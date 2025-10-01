from __future__ import annotations

from typing import List, Optional

from urllib import error as urlerror

from .cache import TTLCache

from . import mappers
from .models import ListSummary, Profile
from .parsers import (
    AddCommand,
    CommandType,
    DueCommand,
    FindCommand,
    LoginCommand,
    OpenCommand,
    ParsedCommand,
    ParseError,
    UseCommand,
    DoneCommand,
    parse_query,
)
from .profiles import ProfileNotFoundError, ProfilesStore
from .vikunja_client import VikunjaApiError, VikunjaClient


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def throw_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancelledError()


class CancelledError(RuntimeError):
    pass


class CommandRouter:
    def __init__(self, profiles: ProfilesStore, client: VikunjaClient, list_cache_ttl: int = 60) -> None:
        self._profiles = profiles
        self._client = client
        self._list_cache: TTLCache[str, List[ListSummary]] = TTLCache(ttl=list_cache_ttl)

    def handle(self, raw_query: str, cancel_token: Optional[CancelToken] = None) -> List[dict]:
        try:
            parsed = parse_query(raw_query)

            if parsed.type == CommandType.HELP:
                return self._help()
            if parsed.type == CommandType.LOGIN:
                return [self._login(parsed)]
            if parsed.type == CommandType.USE:
                return [self._use(parsed)]
            if parsed.type == CommandType.LISTS:
                return self._lists(cancel_token)
            if parsed.type == CommandType.ADD:
                return [self._add(parsed)]
            if parsed.type == CommandType.FIND:
                return self._find(parsed, cancel_token)
            if parsed.type == CommandType.DUE:
                return self._due(parsed, cancel_token)
            if parsed.type == CommandType.DONE:
                return [self._done(parsed)]
            if parsed.type == CommandType.OPEN:
                return [self._open(parsed)]
            return self._help()
        except CancelledError:
            return []
        except ProfileNotFoundError as exc:
            return [mappers.error_result("Profile not found", str(exc))]
        except VikunjaApiError as exc:
            subtitle = ""
            if exc.status_code in (401, 403):
                subtitle = "Access denied. Refresh token with 'vik login <profile> --token <token>'."
            elif exc.status_code in (None, 0):
                subtitle = "Check your network connection or TLS settings."
            return [mappers.error_result(str(exc), subtitle)]
        except RuntimeError as exc:
            return [mappers.error_result("Secure storage error", str(exc))]
        except urlerror.URLError as exc:
            reason = getattr(exc, "reason", "")
            reason_text = str(reason) or str(exc)
            if hasattr(reason, "__class__") and reason.__class__.__name__ == "SSLCertVerificationError":
                return [mappers.error_result("TLS validation failed", "Disable with --verify-tls false if you trust the host.")]
            return [mappers.error_result("Network error", reason_text)]
        except ParseError as exc:
            return [mappers.error_result("Invalid command", str(exc))]

    # Command implementations -------------------------------------------
    def _login(self, command: LoginCommand) -> dict:
        existing = None
        try:
            existing = self._profiles.get_profile(command.profile, include_secret=False)
        except ProfileNotFoundError:
            pass

        base_url = command.base_url or (existing.base_url if existing else None)
        if not base_url:
            raise ParseError("login requires --url when creating a new profile")

        verify_tls = command.verify_tls if command.verify_tls is not None else (existing.verify_tls if existing else True)
        default_list_id = existing.default_list_id if existing else None
        if command.default_list:
            try:
                default_list_id = int(command.default_list)
            except ValueError as exc:
                raise ParseError("--default-list must be a numeric list id") from exc

        token = command.token
        auth_method = "token"
        if command.username and command.password:
            token = self._client.login(base_url, command.username, command.password, verify_tls)
            auth_method = "login"
        elif command.username or command.password:
            raise ParseError("login requires both --username and --password")
        if not token:
            raise ParseError("login requires either --token or username/password")

        profile = Profile(
            name=command.profile,
            base_url=base_url,
            auth_method=auth_method,
            verify_tls=verify_tls,
            default_list_id=default_list_id,
            token=token,
        )

        if not self._client.verify_token(profile):
            raise VikunjaApiError("Unable to verify token", status_code=401)
        self._profiles.save_profile(profile, token)
        self._profiles.set_active(profile.name)
        self._list_cache.pop(profile.name, None)
        return mappers.info_result("Profile saved", f"Active profile: {profile.name}")

    def _use(self, command: UseCommand) -> dict:
        self._profiles.set_active(command.profile)
        return mappers.info_result("Switched profile", f"Active profile: {command.profile}")

    def _lists(self, cancel_token: Optional[CancelToken]) -> List[dict]:
        profile = self._profiles.get_active_profile()
        lists = self._get_lists(profile, cancel_token)
        return [mappers.list_result(item) for item in lists]

    def _add(self, command: AddCommand) -> dict:
        profile = self._profiles.get_active_profile()
        list_id = self._resolve_list_id(profile, command.list_name)
        due_iso = None
        if command.due:
            due_iso = f"{command.due}T00:00:00Z"
        task = self._client.create_task(
            profile,
            list_id=list_id,
            title=command.title,
            description=command.description,
            due=due_iso,
        )
        self._list_cache.pop(profile.name, None)
        return mappers.task_result(task)

    def _find(self, command: FindCommand, cancel_token: Optional[CancelToken]) -> List[dict]:
        profile = self._profiles.get_active_profile()
        cancel_token = cancel_token or CancelToken()
        cancel_token.throw_if_cancelled()
        results = self._client.search_tasks(profile, command.terms, page=command.page)
        cancel_token.throw_if_cancelled()
        items = [mappers.task_result(task) for task in results.tasks]
        if results.has_more:
            next_page_query = f"vik find {command.terms} --page {results.page + 1}"
            items.append(mappers.show_more_result("find", results.page, next_page_query))
        if not items:
            items.append(mappers.info_result("No tasks found", f"Query: {command.terms}"))
        return items

    def _due(self, command: DueCommand, cancel_token: Optional[CancelToken]) -> List[dict]:
        profile = self._profiles.get_active_profile()
        cancel = cancel_token or CancelToken()
        cancel.throw_if_cancelled()
        results = self._client.due_tasks(profile, command.period, page=command.page)
        cancel.throw_if_cancelled()
        items = [mappers.task_result(task) for task in results.tasks]
        if results.has_more:
            next_query = f"vik due {command.period} --page {results.page + 1}"
            items.append(mappers.show_more_result("due", results.page, next_query))
        if not items:
            items.append(mappers.info_result("Nothing due", mappers.due_subtitle(command.period)))
        return items

    def _done(self, command: DoneCommand) -> dict:
        profile = self._profiles.get_active_profile()
        task = self._client.complete_task(profile, command.task_id)
        return mappers.info_result("Task completed", f"Marked '{task.title}' done")

    def _open(self, command: OpenCommand) -> dict:
        profile = self._profiles.get_active_profile()
        task = self._client.get_task(profile, command.task_id)
        return mappers.task_result(task)

    # Helpers ------------------------------------------------------------
    def _help(self) -> List[dict]:
        lines = [
            "vik login <profile> --url https://host --token <token>",
            "vik use <profile>",
            'vik add "Title" --list "Inbox" --due 2024-12-31',
            "vik find search terms",
            "vik due today|tomorrow|week",
            "vik lists",
            "vik done <task_id>",
            "vik open <task_id>",
        ]
        return [mappers.info_result("Vikunja Flow", " | ".join(lines))]

    def _get_lists(self, profile: Profile, cancel_token: Optional[CancelToken]) -> List[ListSummary]:
        cached = self._list_cache.get(profile.name)
        if cached is not None:
            return cached
        cancel = cancel_token or CancelToken()
        cancel.throw_if_cancelled()
        lists, _ = self._client.get_lists(profile)
        cancel.throw_if_cancelled()
        self._list_cache.set(profile.name, lists)
        return lists

    def _resolve_list_id(self, profile: Profile, list_name: Optional[str]) -> int:
        if list_name:
            lists = self._get_lists(profile, None)
            matches = [l for l in lists if l.title.lower() == list_name.lower()]
            if not matches:
                # attempt contains match
                matches = [l for l in lists if list_name.lower() in l.title.lower()]
            if not matches:
                raise VikunjaApiError(f"List '{list_name}' not found")
            if len(matches) > 1:
                raise VikunjaApiError(f"Multiple lists match '{list_name}'")
            return matches[0].id
        if profile.default_list_id:
            return profile.default_list_id
        raise VikunjaApiError("No list specified and no default list configured. Use vik login <profile> --default-list <list_id> or pass --list.")
