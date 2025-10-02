from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from .models import ListSummary, Task

ICON_APP = "Images/app.png"
ICON_LIST = ICON_APP
ICON_TASK = ICON_APP


def task_result(task: Task) -> Dict[str, Any]:
    subtitle_parts = []
    if task.due_date:
        subtitle_parts.append(f"Due {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}")
    if task.list_id:
        subtitle_parts.append(f"List #{task.list_id}")
    if task.done:
        subtitle_parts.append("Completed")
    subtitle = " | ".join(subtitle_parts) if subtitle_parts else "Enter: open • Alt: complete • Ctrl: copy link"
    return {
        "Title": task.title,
        "SubTitle": subtitle,
        "IcoPath": ICON_TASK,
        "JsonRPCAction": {"method": "open_task", "parameters": [task.id]},
        "ContextData": {"task_id": task.id, "url": task.url or ""},
    }


def list_result(list_summary: ListSummary) -> Dict[str, Any]:
    return {
        "Title": list_summary.title,
        "SubTitle": f"List #{list_summary.id}",
        "IcoPath": ICON_LIST,
    }


def info_result(title: str, subtitle: str = "") -> Dict[str, Any]:
    return {
        "Title": title,
        "SubTitle": subtitle,
        "IcoPath": ICON_APP,
    }


def error_result(title: str, subtitle: str = "") -> Dict[str, Any]:
    result = info_result(title, subtitle)
    result["IcoPath"] = ICON_APP
    return result


def show_more_result(command: str, page: int, auto_complete: Optional[str] = None) -> Dict[str, Any]:
    return {
        "Title": "Show more…",
        "SubTitle": "Load more results",
        "IcoPath": ICON_APP,
        "JsonRPCAction": {"method": "noop", "parameters": []},
        "DontHideAfterAction": True,
        "AutoCompleteText": auto_complete,
    }


def due_subtitle(period: str) -> str:
    mapping = {
        "today": "Tasks due today",
        "tomorrow": "Tasks due tomorrow",
        "week": "Tasks due this week",
    }
    return mapping.get(period, "")
