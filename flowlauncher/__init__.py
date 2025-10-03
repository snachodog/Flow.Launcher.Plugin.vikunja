"""Minimal Flow Launcher Python host integration.

This module provides a subset of the original flowlauncher Python SDK so that
plugins can run without requiring an external dependency at runtime. The
implementation supports the JSON-RPC entry points used by :class:`FlowLauncher`
subclasses and a couple of helper methods commonly relied upon by plugins.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Optional


class FlowLauncher:
    """Base class for Flow Launcher Python plugins.

    Flow Launcher invokes the plugin by executing the plugin entry point with a
    JSON-RPC style command line payload. The original SDK dispatches the
    commands automatically. This reimplementation mirrors that behaviour for the
    subset of features required by the Vikunja Flow plugin.
    """

    def __init__(self) -> None:
        # When the plugin is invoked from Flow Launcher, arguments are passed as
        # ``<method> <json_payload>``. When launched manually (for example when
        # running unit tests) no dispatching should happen.
        if len(sys.argv) <= 1:
            return

        method = sys.argv[1]
        payload: Any = None
        if len(sys.argv) > 2:
            payload = json.loads(sys.argv[2])

        self._dispatch(method, payload)

    # ------------------------------------------------------------------
    # Dispatch helpers
    def _dispatch(self, method: str, payload: Any) -> None:
        handler = getattr(self, method, None)
        if handler is None:
            return

        if method == "query":
            query = ""
            if isinstance(payload, dict):
                query = payload.get("search", "") or payload.get("Query", "") or ""
            elif isinstance(payload, str):
                query = payload
            result = handler(query)  # type: ignore[misc]
            self._write_response(result)
            return

        if method == "context_menu":
            data = payload if isinstance(payload, dict) else {}
            result = handler(data)  # type: ignore[misc]
            self._write_response(result)
            return

        if isinstance(payload, list):
            handler(*payload)
        elif payload is None:
            handler()
        else:
            handler(payload)

    def _write_response(self, result: Optional[Iterable[dict]]) -> None:
        if result is None:
            return
        try:
            data = list(result)
        except TypeError:
            data = result  # type: ignore[assignment]
        sys.stdout.write(json.dumps(data))
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Convenience helpers reimplemented for compatibility
    def show_msg(self, title: str, sub_title: str = "", icon_path: Optional[str] = None) -> None:
        message = {"title": title, "sub_title": sub_title, "icon_path": icon_path}
        sys.stdout.write(json.dumps({"method": "show_msg", "data": message}))
        sys.stdout.flush()

    def open_url(self, url: str) -> None:
        sys.stdout.write(json.dumps({"method": "open_url", "data": url}))
        sys.stdout.flush()

    def close_app(self) -> None:
        sys.stdout.write(json.dumps({"method": "close_app"}))
        sys.stdout.flush()

    def change_query(self, query: str) -> None:
        sys.stdout.write(json.dumps({"method": "change_query", "data": query}))
        sys.stdout.flush()

    def save_setting(self, key: str, value: Any) -> None:
        settings_path = self._settings_path()
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except Exception:
                settings = {}
        settings[key] = value
        settings_path.write_text(json.dumps(settings), encoding="utf-8")

    def load_setting(self, key: str, default: Any = None) -> Any:
        settings_path = self._settings_path()
        if not settings_path.exists():
            return default
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            return default
        return settings.get(key, default)

    def _settings_path(self) -> Path:
        base = os.environ.get("FLOW_LAUNCHER_USERDATA")
        if not base:
            base = os.path.join(Path.home(), ".flowlauncher")
        return Path(base) / "settings.json"


__all__ = ["FlowLauncher"]
