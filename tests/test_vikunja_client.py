import json
from urllib import error as urlerror

import pytest

from vikunja_flow.models import Profile
from vikunja_flow.vikunja_client import VikunjaClient, VikunjaApiError


class FakeResponse:
    def __init__(self, status: int, payload, headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    def read(self):
        if isinstance(self._payload, (bytes, bytearray)):
            return bytes(self._payload)
        return json.dumps(self._payload).encode("utf-8")


class FakeOpener:
    def __init__(self):
        self.responses = {}

    def when(self, method: str, url: str, response):
        self.responses[(method.upper(), url)] = response

    def open(self, req, data=None, timeout=None):
        method = req.get_method()
        url = req.full_url
        key = (method, url)
        resp = self.responses.get(key)
        if isinstance(resp, Exception):
            raise resp
        if resp is None:
            raise AssertionError(f"Unexpected request {method} {url}")
        return resp


@pytest.fixture
def profile():
    return Profile(
        name='home',
        base_url='https://vik.example',
        auth_method='token',
        verify_tls=True,
        token='token-123',
    )


def test_login_success():
    opener = FakeOpener()
    opener.when('POST', 'https://vik.example/auth/login', FakeResponse(200, {'token': 'abc'}))
    client = VikunjaClient(opener)
    token = client.login('https://vik.example', 'user', 'pass')
    assert token == 'abc'


def test_create_task(profile):
    opener = FakeOpener()
    opener.when('POST', 'https://vik.example/lists/5/tasks', FakeResponse(200, {'id': 1, 'title': 'Test', 'list_id': 5, 'done': False}))
    client = VikunjaClient(opener)
    task = client.create_task(profile, list_id=5, title='Test')
    assert task.id == 1
    assert task.title == 'Test'


def test_get_lists(profile):
    headers = {
        'X-Pagination-Page': '1',
        'X-Pagination-Limit': '50',
        'X-Pagination-TotalPages': '1',
        'X-Pagination-Total': '1',
    }
    opener = FakeOpener()
    opener.when('GET', 'https://vik.example/lists?page=1&per_page=50', FakeResponse(200, [{'id': 99, 'title': 'Inbox'}], headers=headers))
    client = VikunjaClient(opener)
    lists, pagination = client.get_lists(profile)
    assert lists[0].title == 'Inbox'
    assert pagination.total_count == 1


def test_error_raises_exception(profile):
    opener = FakeOpener()
    from io import BytesIO

    error_payload = BytesIO(json.dumps({'message': 'invalid token'}).encode('utf-8'))
    error = urlerror.HTTPError('https://vik.example/tasks/1', 401, 'unauthorized', {}, error_payload)
    opener.when('GET', 'https://vik.example/tasks/1', error)
    client = VikunjaClient(opener)
    with pytest.raises(VikunjaApiError):
        client.get_task(profile, 1)
