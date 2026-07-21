import pathlib

import pytest

from things_mcp import writes


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    writes._TOKEN_CACHE.clear()
    # No real waiting during read-back polling.
    monkeypatch.setattr(writes.time, "sleep", lambda *a, **k: None)
    yield
    writes._TOKEN_CACHE.clear()


def _sequence(*batches):
    """Return a callable that yields successive listings on each call."""
    calls = {"n": 0}

    def lister():
        i = min(calls["n"], len(batches) - 1)
        calls["n"] += 1
        return list(batches[i])

    return lister


def test_add_todo_confirms_only_newly_appeared_uuid(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    # snapshot: one old item; after: old + new same-nothing, plus the new one.
    lister = _sequence(
        [{"title": "Test", "uuid": "old"}],  # before snapshot
        [{"title": "Test", "uuid": "old"}, {"title": "Test", "uuid": "new"}],  # after
    )
    monkeypatch.setattr(writes.reads, "list_todos", lister)

    result = writes.add_todo("Test")
    assert result["ok"] is True
    assert ran["url"].startswith("things:///add?")
    assert result["match"]["uuid"] == "new"


def test_add_todo_preexisting_same_title_not_falsely_confirmed(monkeypatch):
    """If the write silently failed and a same-title item already existed,
    match must be None (no fabricated confirmation)."""
    monkeypatch.setattr(writes.runner, "run_url", lambda url: None)
    lister = _sequence(
        [{"title": "Dup", "uuid": "old"}],  # before
        [{"title": "Dup", "uuid": "old"}],  # after: unchanged (write no-op)
    )
    monkeypatch.setattr(writes.reads, "list_todos", lister)

    result = writes.add_todo("Dup")
    assert result["match"] is None


def test_add_todo_ambiguous_new_items_returns_none(monkeypatch):
    monkeypatch.setattr(writes.runner, "run_url", lambda url: None)
    lister = _sequence(
        [],  # before
        [{"title": "X", "uuid": "a"}, {"title": "X", "uuid": "b"}],  # two new same-title
    )
    monkeypatch.setattr(writes.reads, "list_todos", lister)

    result = writes.add_todo("X")
    assert result["match"] is None


def test_add_todo_list_target_confirmed_via_all_todos(monkeypatch):
    """A todo added to a list (not the inbox) is still confirmable because the
    read-back scans all todos, not just the inbox."""
    monkeypatch.setattr(writes.runner, "run_url", lambda url: None)
    lister = _sequence(
        [{"title": "Buy milk", "uuid": "existing-in-groceries"}],
        [
            {"title": "Buy milk", "uuid": "existing-in-groceries"},
            {"title": "Buy milk", "uuid": "brand-new"},
        ],
    )
    monkeypatch.setattr(writes.reads, "list_todos", lister)

    result = writes.add_todo("Buy milk", list="Groceries")
    assert "list=Groceries" in result["url"]
    assert result["match"]["uuid"] == "brand-new"


def test_get_token_reads_things_token(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: "TKN")
    monkeypatch.setattr(writes.db, "find_database", lambda: pathlib.Path("/x"))
    assert writes.get_token() == "TKN"


def test_get_token_missing_raises(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: None)
    monkeypatch.setattr(writes.db, "find_database", lambda: pathlib.Path("/x"))
    with pytest.raises(writes.ThingsAuthError):
        writes.get_token()


def test_update_todo_sends_token_but_redacts_in_return(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "SECRET-TOKEN")
    result = writes.update_todo("ABC", title="New")
    # The token IS sent to Things via the runner...
    assert "auth-token=SECRET-TOKEN" in ran["url"]
    assert "id=ABC" in ran["url"]
    # ...but must NOT be returned to the caller/model.
    assert "SECRET-TOKEN" not in result["url"]
    assert "auth-token=<redacted>" in result["url"]


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
