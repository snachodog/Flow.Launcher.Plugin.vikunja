from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class CommandType(str, Enum):
    LOGIN = "login"
    USE = "use"
    ADD = "add"
    FIND = "find"
    DUE = "due"
    LISTS = "lists"
    DONE = "done"
    OPEN = "open"
    HELP = "help"


@dataclass
class ParsedCommand:
    type: CommandType


@dataclass
class LoginCommand(ParsedCommand):
    profile: str
    base_url: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    verify_tls: Optional[bool] = None
    default_list: Optional[str] = None


@dataclass
class UseCommand(ParsedCommand):
    profile: str


@dataclass
class AddCommand(ParsedCommand):
    title: str
    list_name: Optional[str]
    due: Optional[str]
    description: Optional[str]


@dataclass
class FindCommand(ParsedCommand):
    terms: str
    page: int = 1


@dataclass
class DueCommand(ParsedCommand):
    period: str
    page: int = 1


@dataclass
class DoneCommand(ParsedCommand):
    task_id: int


@dataclass
class OpenCommand(ParsedCommand):
    task_id: int


@dataclass
class ListsCommand(ParsedCommand):
    pass


class ParseError(ValueError):
    pass


def _as_bool(value: str) -> bool:
    truthy = {"true", "1", "yes", "y", "on"}
    falsy = {"false", "0", "no", "n", "off"}
    lower = value.lower()
    if lower in truthy:
        return True
    if lower in falsy:
        return False
    raise ParseError(f"Invalid boolean value: {value}")


def parse_query(raw_query: str) -> ParsedCommand:
    tokens = shlex.split(raw_query.strip()) if raw_query else []
    if not tokens:
        return ParsedCommand(CommandType.HELP)

    command = tokens[0].lower()
    remainder = tokens[1:]

    if command == CommandType.LOGIN:
        return _parse_login(remainder)
    if command == CommandType.USE:
        return _parse_use(remainder)
    if command == CommandType.ADD:
        return _parse_add(remainder)
    if command == CommandType.FIND:
        return _parse_find(remainder)
    if command == CommandType.DUE:
        return _parse_due(remainder)
    if command == CommandType.LISTS:
        return ListsCommand(CommandType.LISTS)
    if command == CommandType.DONE:
        return _parse_task_id(CommandType.DONE, remainder)
    if command == CommandType.OPEN:
        return _parse_task_id(CommandType.OPEN, remainder)

    return ParsedCommand(CommandType.HELP)


def _parse_use(tokens: List[str]) -> UseCommand:
    if len(tokens) < 1:
        raise ParseError("use expects a profile name")
    return UseCommand(CommandType.USE, tokens[0])


def _parse_login(tokens: List[str]) -> LoginCommand:
    if not tokens:
        raise ParseError("login expects a profile name")

    profile = tokens[0]
    options = tokens[1:]
    base_url = token = username = password = default_list = None
    verify_tls: Optional[bool] = None

    idx = 0
    while idx < len(options):
        key = options[idx].lower()
        if key in {"--url", "--base", "--base-url"}:
            idx += 1
            base_url = _expect_value(options, idx, key)
        elif key == "--token":
            idx += 1
            token = _expect_value(options, idx, key)
        elif key in {"--username", "--user"}:
            idx += 1
            username = _expect_value(options, idx, key)
        elif key in {"--password", "--pass"}:
            idx += 1
            password = _expect_value(options, idx, key)
        elif key in {"--verify-tls", "--verify"}:
            idx += 1
            verify_tls = _as_bool(_expect_value(options, idx, key))
        elif key in {"--default-list", "--list"}:
            idx += 1
            default_list = _expect_value(options, idx, key)
        else:
            raise ParseError(f"Unknown option for login: {options[idx]}")
        idx += 1

    return LoginCommand(
        type=CommandType.LOGIN,
        profile=profile,
        base_url=base_url,
        token=token,
        username=username,
        password=password,
        verify_tls=verify_tls,
        default_list=default_list,
    )


def _parse_add(tokens: List[str]) -> AddCommand:
    if not tokens:
        raise ParseError("add expects a task title")
    title = tokens[0]
    options = tokens[1:]
    list_name = due = description = None
    idx = 0
    while idx < len(options):
        key = options[idx].lower()
        if key == "--list":
            idx += 1
            list_name = _expect_value(options, idx, key)
        elif key == "--due":
            idx += 1
            due = _expect_value(options, idx, key)
        elif key == "--desc":
            idx += 1
            description = _expect_value(options, idx, key)
        else:
            raise ParseError(f"Unknown option for add: {options[idx]}")
        idx += 1
    return AddCommand(CommandType.ADD, title, list_name, due, description)


def _parse_find(tokens: List[str]) -> FindCommand:
    if not tokens:
        raise ParseError("find expects search terms")
    terms: List[str] = []
    page = 1
    idx = 0
    while idx < len(tokens):
        if tokens[idx] == "--page":
            idx += 1
            value = _expect_value(tokens, idx, "--page")
            try:
                page = max(1, int(value))
            except ValueError as exc:
                raise ParseError("--page must be a positive integer") from exc
        else:
            terms.append(tokens[idx])
        idx += 1
    if not terms:
        raise ParseError("find expects search terms")
    return FindCommand(CommandType.FIND, " ".join(terms), page)


def _parse_due(tokens: List[str]) -> DueCommand:
    if not tokens:
        raise ParseError("due expects a period (today, tomorrow, week)")
    period = tokens[0].lower()
    if period not in {"today", "tomorrow", "week"}:
        raise ParseError("due period must be today, tomorrow, or week")
    page = 1
    idx = 1
    while idx < len(tokens):
        if tokens[idx] == "--page":
            idx += 1
            value = _expect_value(tokens, idx, "--page")
            try:
                page = max(1, int(value))
            except ValueError as exc:
                raise ParseError("--page must be a positive integer") from exc
        else:
            raise ParseError(f"Unknown option for due: {tokens[idx]}")
        idx += 1
    return DueCommand(CommandType.DUE, period, page)


def _parse_task_id(command: CommandType, tokens: List[str]) -> ParsedCommand:
    if not tokens:
        raise ParseError(f"{command.value} expects a task id")
    try:
        task_id = int(tokens[0])
    except ValueError as exc:
        raise ParseError("Task id must be an integer") from exc
    cls = DoneCommand if command == CommandType.DONE else OpenCommand
    return cls(command, task_id)


def _expect_value(options: List[str], idx: int, key: str) -> str:
    if idx >= len(options):
        raise ParseError(f"Option {key} expects a value")
    return options[idx]
