import asyncio
import pathlib

from things_mcp import server, db, reads


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_inbox", "list_today", "list_upcoming", "list_anytime",
        "list_someday", "list_logbook", "list_todos", "list_projects",
        "list_areas", "list_tags", "search", "get_item", "list_recent",
        "add_todo", "add_project", "update_todo", "update_project",
        "complete_todo", "cancel_todo", "doctor",
    }
    assert expected <= names


def test_list_areas_tool_returns_data(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    out = server.list_areas()
    assert isinstance(out, list)


def test_read_tool_errors_are_caught(monkeypatch):
    def boom():
        raise db.ThingsDBPermissionError("FDA needed")

    monkeypatch.setattr(reads, "list_inbox", boom)
    out = server.list_inbox()
    assert isinstance(out, dict) and "error" in out


def test_invalid_status_returns_friendly_error(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    out = server.list_todos(status="not-a-real-status")
    assert isinstance(out, dict) and "error" in out


def test_invalid_offset_returns_friendly_error(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    out = server.list_recent("7")  # missing unit like '7d'
    assert isinstance(out, dict) and "error" in out
