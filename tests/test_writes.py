import pathlib

import pytest

from things_mcp import writes


@pytest.fixture(autouse=True)
def _reset_token_cache():
    writes._TOKEN_CACHE.clear()
    yield
    writes._TOKEN_CACHE.clear()


def test_add_todo_builds_and_runs(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes.reads, "list_inbox", lambda: [{"title": "Test", "uuid": "u1"}])

    result = writes.add_todo("Test")
    assert result["ok"] is True
    assert ran["url"].startswith("things:///add?")
    assert result["match"]["uuid"] == "u1"


def test_get_token_reads_things_token(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: "TKN")
    monkeypatch.setattr(writes.db, "find_database", lambda: pathlib.Path("/x"))
    assert writes.get_token() == "TKN"


def test_get_token_missing_raises(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: None)
    monkeypatch.setattr(writes.db, "find_database", lambda: pathlib.Path("/x"))
    with pytest.raises(writes.ThingsAuthError):
        writes.get_token()


def test_update_todo_includes_token(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    result = writes.update_todo("ABC", title="New")
    assert "auth-token=TKN" in ran["url"]
    assert "id=ABC" in ran["url"]
    assert result["ok"] is True


def test_complete_todo_sets_completed(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    writes.complete_todo("ABC")
    assert "completed=true" in ran["url"]


def test_cancel_todo_sets_canceled(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    writes.cancel_todo("ABC")
    assert "canceled=true" in ran["url"]
