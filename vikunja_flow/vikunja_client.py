from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urlerror, parse, request

from .models import ListSummary, PaginatedTasks, Profile, Task

API_TIMEOUT = 8


class VikunjaApiError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Pagination:
    page: int
    per_page: int
    total_pages: int
    total_count: int

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> "Pagination":
        return cls(
            page=int(headers.get("X-Pagination-Page", "1")),
            per_page=int(headers.get("X-Pagination-Limit", "50")),
            total_pages=int(headers.get("X-Pagination-TotalPages", "1")),
            total_count=int(headers.get("X-Pagination-Total", "0")),
        )


class VikunjaClient:
    def __init__(self, opener: Optional[request.OpenerDirector] = None) -> None:
        self._opener = opener or request.build_opener()

    # Authentication --------------------------------------------------
    def login(self, base_url: str, username: str, password: str, verify_tls: bool = True) -> str:
        payload = {"username": username, "password": password}
        response = self._execute(
            base_url,
            "POST",
            "/auth/login",
            data=payload,
            verify_tls=verify_tls,
        )
        data = self._read_json(response)
        token = data.get("token")
        if not token:
            raise VikunjaApiError("Login succeeded but no token returned")
        return token

    def verify_token(self, profile: Profile) -> bool:
        response = self._execute_profile(profile, "GET", "/user")
        data = self._read_json(response)
        return bool(data.get("id"))

    # Lists -----------------------------------------------------------
    def get_lists(self, profile: Profile, page: int = 1, per_page: int = 50) -> Tuple[List[ListSummary], Pagination]:
        response = self._execute_profile(
            profile,
            "GET",
            "/lists",
            params={"page": page, "per_page": per_page},
        )
        data = self._read_json(response)
        pagination = Pagination.from_headers(dict(response.headers))
        lists = [ListSummary(id=item["id"], title=item["title"]) for item in data]
        return lists, pagination

    # Tasks -----------------------------------------------------------
    def create_task(
        self,
        profile: Profile,
        list_id: int,
        title: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
    ) -> Task:
        payload: Dict[str, Any] = {"title": title}
        if description:
            payload["description"] = description
        if due:
            payload["due_date"] = due
        response = self._execute_profile(profile, "POST", f"/lists/{list_id}/tasks", data=payload)
        return self._task_from_payload(self._read_json(response), profile)

    def search_tasks(self, profile: Profile, query: str, page: int = 1, per_page: int = 20) -> PaginatedTasks:
        response = self._execute_profile(
            profile,
            "GET",
            "/tasks/all",
            params={"search": query, "page": page, "per_page": per_page},
        )
        payload = self._read_json(response)
        pagination = Pagination.from_headers(dict(response.headers))
        tasks = [self._task_from_payload(item, profile) for item in payload]
        return PaginatedTasks(tasks, pagination.page, pagination.total_pages, pagination.total_count, pagination.page < pagination.total_pages)

    def due_tasks(self, profile: Profile, period: str, page: int = 1, per_page: int = 20) -> PaginatedTasks:
        now = datetime.utcnow()
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == "tomorrow":
            start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        else:
            start = now
            end = now + timedelta(days=7)
        response = self._execute_profile(
            profile,
            "GET",
            "/tasks/all",
            params={
                "due_date_from": start.isoformat() + "Z",
                "due_date_to": end.isoformat() + "Z",
                "sort_by": "due_date",
                "order": "asc",
                "page": page,
                "per_page": per_page,
            },
        )
        payload = self._read_json(response)
        pagination = Pagination.from_headers(dict(response.headers))
        tasks = [self._task_from_payload(item, profile) for item in payload]
        return PaginatedTasks(tasks, pagination.page, pagination.total_pages, pagination.total_count, pagination.page < pagination.total_pages)

    def complete_task(self, profile: Profile, task_id: int) -> Task:
        response = self._execute_profile(profile, "PUT", f"/tasks/{task_id}", data={"done": True})
        return self._task_from_payload(self._read_json(response), profile)

    def get_task(self, profile: Profile, task_id: int) -> Task:
        response = self._execute_profile(profile, "GET", f"/tasks/{task_id}")
        return self._task_from_payload(self._read_json(response), profile)

    # Helpers ---------------------------------------------------------
    def _execute_profile(
        self,
        profile: Profile,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        if not profile.token:
            raise VikunjaApiError("Profile does not have an access token")
        headers = {"Authorization": f"Bearer {profile.token}"}
        return self._execute(profile.base_url, method, path, params=params, data=data, headers=headers, verify_tls=profile.verify_tls)

    def _execute(
        self,
        base_url: str,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        verify_tls: bool = True,
    ):
        url = self._url(base_url, path)
        if params:
            query = parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"
        body = None
        req = request.Request(url, method=method.upper())
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        try:
            opener = self._opener
            if not verify_tls and url.startswith("https"):
                context = ssl._create_unverified_context()
                opener = request.build_opener(request.HTTPSHandler(context=context))
            response = opener.open(req, data=body, timeout=API_TIMEOUT)  # type: ignore[arg-type]
            return response
        except urlerror.HTTPError as exc:
            message = self._extract_error_message(exc)
            raise VikunjaApiError(message, status_code=exc.code) from None

    def _read_json(self, response) -> Any:
        if response.status == 204:
            return {}
        data = response.read()
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))

    def _extract_error_message(self, exc: urlerror.HTTPError) -> str:
        try:
            data = exc.read()
            if data:
                payload = json.loads(data.decode("utf-8"))
                if isinstance(payload, dict):
                    return payload.get("message") or payload.get("error") or exc.reason
        except Exception:
            pass
        return str(exc.reason)

    def _url(self, base_url: str, path: str) -> str:
        base = base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def _task_from_payload(self, data: Dict[str, Any], profile: Profile) -> Task:
        due = None
        due_raw = data.get("due_date")
        if due_raw:
            try:
                due = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
            except ValueError:
                due = None
        return Task(
            id=data["id"],
            title=data.get("title", "(untitled)"),
            description=data.get("description"),
            list_id=data.get("list_id"),
            due_date=due,
            done=data.get("done", False),
            url=self.build_task_url(profile, data["id"]),
        )

    def build_task_url(self, profile: Profile, task_id: int) -> str:
        return f"{profile.base_url.rstrip('/')}/tasks/{task_id}"
