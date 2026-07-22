import pytest

from things_mcp import applescript as a

US = "\x1f"
RS = "\x1e"


def _todo_row(uuid, name, status="open", notes="", deadline="", start="", tags="", created="2026-07-01"):
    return US.join([uuid, name, status, notes, deadline, start, tags, created])


def _fake_run(output):
    return lambda script: output


def test_list_todos_parses_and_maps_status(monkeypatch):
    raw = _todo_row("u1", "Buy milk", status="open", tags="Home, Errand") + RS
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    todos = a.list_todos()
    assert len(todos) == 1
    t = todos[0]
    assert t["uuid"] == "u1"
    assert t["title"] == "Buy milk"
    assert t["type"] == "to-do"
    assert t["status"] == "incomplete"  # 'open' mapped
    assert t["tags"] == ["Home", "Errand"]


def test_trailing_newline_does_not_create_phantom(monkeypatch):
    # osascript appends a trailing newline after the final record separator.
    raw = _todo_row("u1", "real") + RS + "\n"
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    todos = a.list_todos()
    assert len(todos) == 1
    assert todos[0]["uuid"] == "u1"


def test_list_areas_ignores_trailing_newline(monkeypatch):
    raw = US.join(["a1", "Personal"]) + RS + "\n"
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    assert a.list_areas() == [{"uuid": "a1", "type": "area", "title": "Personal"}]


def test_list_todos_default_aggregates_open_lists(monkeypatch):
    scripts = []

    def cap(script):
        scripts.append(script)
        return _todo_row("u1", "x") + RS

    monkeypatch.setattr(a, "_run", cap)
    todos = a.list_todos()
    joined = "\n".join(scripts)
    # Aggregates the built-in incomplete lists, never scans the Logbook.
    assert 'list "Inbox"' in joined and 'list "Anytime"' in joined
    assert 'list "Logbook"' not in joined
    # Same uuid returned by each list is de-duplicated.
    assert [t["uuid"] for t in todos] == ["u1"]


def test_list_todos_completed_reads_logbook(monkeypatch):
    seen = {}

    def cap(script):
        seen["script"] = script
        return _todo_row("u1", "done", status="completed") + RS

    monkeypatch.setattr(a, "_run", cap)
    todos = a.list_todos(status="completed")
    assert 'list "Logbook"' in seen["script"]
    assert [t["uuid"] for t in todos] == ["u1"]


def test_list_recent_filters_open_todos_by_created(monkeypatch):
    # today is 2026-07-21; '3d' cutoff = 2026-07-18
    raw = (
        _todo_row("recent", "new one", created="2026-07-20")
        + RS
        + _todo_row("old", "old one", created="2026-01-01")
        + RS
    )
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    recent = a.list_recent("3d")
    assert [t["uuid"] for t in recent] == ["recent"]


def test_list_todos_tag_filter(monkeypatch):
    raw = (
        _todo_row("u1", "a", tags="Home")
        + RS
        + _todo_row("u2", "b", tags="Work")
        + RS
    )
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    todos = a.list_todos(tag="Work")
    assert [t["uuid"] for t in todos] == ["u2"]


def test_search_matches_title_and_notes(monkeypatch):
    raw = (
        _todo_row("u1", "Groceries", notes="milk and eggs")
        + RS
        + _todo_row("u2", "Taxes", notes="file 1040")
        + RS
    )
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    assert [t["uuid"] for t in a.search("milk")] == ["u1"]
    assert [t["uuid"] for t in a.search("taxes")] == ["u2"]


def test_list_tags(monkeypatch):
    monkeypatch.setattr(a, "_run", _fake_run("Home" + RS + "Work" + RS))
    assert a.list_tags() == ["Home", "Work"]


def test_list_areas(monkeypatch):
    raw = US.join(["area1", "Personal"]) + RS + US.join(["area2", "Work"]) + RS
    monkeypatch.setattr(a, "_run", _fake_run(raw))
    areas = a.list_areas()
    assert areas == [
        {"uuid": "area1", "type": "area", "title": "Personal"},
        {"uuid": "area2", "type": "area", "title": "Work"},
    ]


def test_get_item_todo(monkeypatch):
    # type, id, name, status, notes, deadline, start, tags, created
    row = US.join(
        ["to-do", "u9", "My todo", "open", "notes", "2026-08-01", "", "Home", "2026-07-01"]
    )
    monkeypatch.setattr(a, "_run", _fake_run(row))
    item = a.get_item("u9")
    assert item["uuid"] == "u9"
    assert item["type"] == "to-do"
    assert item["deadline"] == "2026-08-01"
    assert item["tags"] == ["Home"]


def test_get_item_missing_returns_none(monkeypatch):
    monkeypatch.setattr(a, "_run", _fake_run(""))
    assert a.get_item("nope") is None


def test_get_item_rejects_bad_uuid(monkeypatch):
    with pytest.raises(a.AppleScriptError):
        a.get_item('x"; do bad things')


def test_available_true(monkeypatch):
    monkeypatch.setattr(a, "_run", _fake_run("3.22.12\n"))
    assert a.available() is True


def test_available_false_on_error(monkeypatch):
    def boom(script):
        raise a.AppleScriptError("nope")

    monkeypatch.setattr(a, "_run", boom)
    assert a.available() is False


def test_offset_to_days_valid():
    assert a._offset_to_days("3d") == 3
    assert a._offset_to_days("2w") == 14
    assert a._offset_to_days("1y") == 365
    with pytest.raises(ValueError):
        a._offset_to_days("7")  # missing unit
