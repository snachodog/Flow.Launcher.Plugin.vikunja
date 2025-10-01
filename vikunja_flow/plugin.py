from __future__ import annotations

import platform
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

from flowlauncher import FlowLauncher

from .profiles import ProfilesStore, ProfileNotFoundError
from .vikunja_client import VikunjaClient, VikunjaApiError
from .router import CommandRouter, CancelToken

class VikunjaFlowPlugin(FlowLauncher):
    def __init__(self) -> None:
        self._base_path = Path(__file__).resolve().parent
        data_dir = self._base_path / "data"
        self._profiles = ProfilesStore(data_dir / "profiles.json")
        self._client = VikunjaClient()
        self._router = CommandRouter(self._profiles, self._client)
        self._active_token: Optional[CancelToken] = None
        super().__init__()

    # Flow entry points -------------------------------------------------
    def query(self, query: str) -> list[dict]:  # type: ignore[override]
        if self._active_token:
            self._active_token.cancel()
        token = CancelToken()
        self._active_token = token
        results = self._router.handle(query, token)
        # clear token to avoid cancelling follow-up actions triggered by selection
        self._active_token = None
        return results

    def context_menu(self, data: Dict[str, Any]) -> list[dict]:  # type: ignore[override]
        if not isinstance(data, dict) or "task_id" not in data:
            return []
        task_id = data.get("task_id")
        url = data.get("url")
        return [
            {
                "Title": "Open in browser",
                "JsonRPCAction": {"method": "open_task", "parameters": [task_id]},
            },
            {
                "Title": "Mark complete",
                "JsonRPCAction": {"method": "complete_task", "parameters": [task_id]},
            },
            {
                "Title": "Copy link",
                "JsonRPCAction": {"method": "copy_task_link", "parameters": [url or ""]},
            },
        ]

    # Actions -----------------------------------------------------------
    def open_task(self, task_id: int) -> None:
        try:
            profile = self._profiles.get_active_profile()
        except ProfileNotFoundError:
            return
        url = self._client.build_task_url(profile, task_id)
        webbrowser.open(url)

    def complete_task(self, task_id: int) -> None:
        try:
            profile = self._profiles.get_active_profile()
        except ProfileNotFoundError:
            return
        try:
            self._client.complete_task(profile, task_id)
        except VikunjaApiError:
            pass

    def copy_task_link(self, url: str) -> None:
        if not url:
            return
        if self._copy_with_tk(url):
            return
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["pbcopy"], input=url, text=True, check=True)
            elif system == "Windows":
                self._copy_windows(url)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=url, text=True, check=True)
        except Exception:
            pass

    def noop(self) -> None:
        return

    def _copy_with_tk(self, text: str) -> bool:
        try:
            import tkinter

            root = tkinter.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return True
        except Exception:
            return False

    def _copy_windows(self, text: str) -> bool:
        try:
            import ctypes

            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if not user32.OpenClipboard(None):
                return False
            try:
                user32.EmptyClipboard()
                size = (len(text) + 1) * ctypes.sizeof(ctypes.c_wchar)
                handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not handle:
                    return False
                buffer = kernel32.GlobalLock(handle)
                if not buffer:
                    kernel32.GlobalFree(handle)
                    return False
                ctypes.memmove(buffer, ctypes.create_unicode_buffer(text), size)
                kernel32.GlobalUnlock(handle)
                user32.SetClipboardData(CF_UNICODETEXT, handle)
                return True
            finally:
                user32.CloseClipboard()
        except Exception:
            return False
