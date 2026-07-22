import pathlib

import pytest

from things_mcp import read_backend, db, applescript
from things_mcp import reads as sqlite_reads


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(read_backend.BACKEND_ENV, raising=False)
    read_backend.reset_cache()
    yield
    read_backend.reset_cache()


def test_env_forces_sqlite(monkeypatch):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "sqlite")
    assert read_backend.active_backend() == "sqlite"


def test_env_forces_applescript(monkeypatch):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "applescript")
    assert read_backend.active_backend() == "applescript"


def test_auto_uses_sqlite_when_db_found(monkeypatch):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path("/x/main.sqlite"))
    assert read_backend.active_backend() == "sqlite"


def test_auto_falls_back_to_applescript_when_db_blocked(monkeypatch):
    def boom():
        raise db.ThingsDBPermissionError("FDA needed")

    monkeypatch.setattr(db, "find_database", boom)
    assert read_backend.active_backend() == "applescript"


def test_auto_falls_back_when_db_not_found(monkeypatch):
    def boom():
        raise db.ThingsDBNotFoundError("no db")

    monkeypatch.setattr(db, "find_database", boom)
    assert read_backend.active_backend() == "applescript"


def test_dispatch_forwards_to_chosen_backend(monkeypatch, fixture_db):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "applescript")
    monkeypatch.setattr(applescript, "list_areas", lambda: [{"uuid": "a1", "title": "X"}])
    assert read_backend.list_areas() == [{"uuid": "a1", "title": "X"}]


def test_choice_is_cached(monkeypatch):
    calls = {"n": 0}

    def counting_find():
        calls["n"] += 1
        return pathlib.Path("/x/main.sqlite")

    monkeypatch.setattr(db, "find_database", counting_find)
    read_backend.active_backend()
    read_backend.active_backend()
    assert calls["n"] == 1  # cached after first resolution
