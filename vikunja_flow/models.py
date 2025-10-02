from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class Profile:
    name: str
    base_url: str
    auth_method: str
    verify_tls: bool = True
    default_list_id: Optional[int] = None
    token: Optional[str] = None

    def requires_login(self) -> bool:
        return self.auth_method == "login"


@dataclass
class ListSummary:
    id: int
    title: str


@dataclass
class Task:
    id: int
    title: str
    description: Optional[str]
    list_id: Optional[int]
    due_date: Optional[datetime]
    done: bool
    url: Optional[str] = None


@dataclass
class PaginatedTasks:
    tasks: List[Task]
    page: int
    total_pages: int
    total_count: int
    has_more: bool
