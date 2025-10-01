import pytest

from vikunja_flow.parsers import parse_query, LoginCommand, FindCommand, DueCommand, ParseError


def test_parse_login_with_token():
    command = parse_query('login personal --url https://vik.example --token secret --verify-tls false --default-list 42')
    assert isinstance(command, LoginCommand)
    assert command.profile == 'personal'
    assert command.base_url == 'https://vik.example'
    assert command.token == 'secret'
    assert command.verify_tls is False
    assert command.default_list == '42'


def test_parse_find_with_page():
    command = parse_query('find overdue invoices --page 3')
    assert isinstance(command, FindCommand)
    assert command.terms == 'overdue invoices'
    assert command.page == 3


def test_parse_find_requires_terms():
    with pytest.raises(ParseError):
        parse_query('find --page 2')


def test_parse_due_with_page():
    command = parse_query('due today --page 2')
    assert isinstance(command, DueCommand)
    assert command.period == 'today'
    assert command.page == 2


def test_parse_login_missing_credentials_defaults():
    command = parse_query('login work --url https://vik.example')
    assert isinstance(command, LoginCommand)
    assert command.token is None
