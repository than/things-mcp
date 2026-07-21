import sqlite3
import pathlib
import pytest

from things_mcp import db


def _make_sqlite(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x)")
    con.close()


def _nested(container: pathlib.Path, sub: str) -> pathlib.Path:
    """Create <container>/<sub>/Things Database.thingsdatabase/main.sqlite."""
    dbfile = container / sub / "Things Database.thingsdatabase" / "main.sqlite"
    _make_sqlite(dbfile)
    return dbfile


def test_env_override_used(tmp_path, monkeypatch):
    dbfile = tmp_path / "main.sqlite"
    _make_sqlite(dbfile)
    monkeypatch.setenv(db.THINGSDB_ENV, str(dbfile))
    assert db.find_database() == dbfile


def test_env_override_missing_file_raises_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv(db.THINGSDB_ENV, str(tmp_path / "nope.sqlite"))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()


def test_permission_denied_container_is_distinct(monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    # No candidates found, but a denial was recorded -> TCC error.
    monkeypatch.setattr(db, "_scan_candidates", lambda: ([], True))
    with pytest.raises(db.ThingsDBPermissionError):
        db.find_database()


def test_not_found_when_no_candidates_and_no_denial(monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    monkeypatch.setattr(db, "_scan_candidates", lambda: ([], False))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()


def test_finds_nested_db_happy_path(tmp_path, monkeypatch):
    """The real scandir walk locates and returns a nested main.sqlite."""
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    container = tmp_path / "container"
    dbfile = _nested(container, "ThingsData-ABC")
    monkeypatch.setattr(db, "GROUP_CONTAINER", container)
    assert db.find_database() == dbfile


def test_prefers_thingsdata_layout_over_legacy(tmp_path, monkeypatch):
    """When both layouts coexist, the current ThingsData-* DB wins (not the
    shallower legacy path)."""
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    container = tmp_path / "container"
    # Legacy flat layout (shorter path).
    legacy = container / "Things Database.thingsdatabase" / "main.sqlite"
    _make_sqlite(legacy)
    # Current layout (deeper path).
    current = _nested(container, "ThingsData-XYZ")
    monkeypatch.setattr(db, "GROUP_CONTAINER", container)
    assert db.find_database() == current


def test_readable_db_returned_despite_blocked_sibling(tmp_path, monkeypatch):
    """A permission-denied sibling directory must not mask an accessible DB
    with a misleading Full Disk Access error (fail open)."""
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    container = tmp_path / "container"
    dbfile = _nested(container, "ThingsData-AAAA")
    blocked = container / "blocked"
    blocked.mkdir()
    blocked.chmod(0o000)
    monkeypatch.setattr(db, "GROUP_CONTAINER", container)
    try:
        assert db.find_database() == dbfile
    finally:
        blocked.chmod(0o755)


def test_real_permission_denied_container_is_tcc(tmp_path, monkeypatch):
    """A container we cannot read at all must raise ThingsDBPermissionError."""
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "inner").mkdir()
    blocked.chmod(0o000)
    monkeypatch.setattr(db, "GROUP_CONTAINER", blocked)
    try:
        with pytest.raises(db.ThingsDBPermissionError):
            db.find_database()
    finally:
        blocked.chmod(0o755)


def test_missing_container_is_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    monkeypatch.setattr(db, "GROUP_CONTAINER", tmp_path / "does-not-exist")
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()
