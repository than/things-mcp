import sqlite3
import pathlib
import pytest

from things_mcp import db


def _make_sqlite(path: pathlib.Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x)")
    con.close()


def test_env_override_used(tmp_path, monkeypatch):
    dbfile = tmp_path / "main.sqlite"
    _make_sqlite(dbfile)
    monkeypatch.setenv(db.THINGSDB_ENV, str(dbfile))
    assert db.find_database() == dbfile


def test_env_override_missing_file_raises_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv(db.THINGSDB_ENV, str(tmp_path / "nope.sqlite"))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()


def test_permission_error_is_distinct(monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)

    def boom(*a, **k):
        raise PermissionError(1, "Operation not permitted")

    # Simulate TCC denial while scanning the container.
    monkeypatch.setattr(db, "_iter_candidate_dbs", boom)
    with pytest.raises(db.ThingsDBPermissionError):
        db.find_database()


def test_not_found_when_glob_empty(monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    monkeypatch.setattr(db, "_iter_candidate_dbs", lambda: iter(()))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()


def test_real_permission_denied_container_is_tcc(tmp_path, monkeypatch):
    """A container we cannot read must raise ThingsDBPermissionError, not NotFound.

    Regression for the glob-swallows-PermissionError bug: pathlib.glob returns
    [] on an unreadable directory, so the manual scandir walk must surface the
    denial instead.
    """
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    # Put a nested dir + db so a swallowing walk would find nothing but a
    # raising walk hits the wall first.
    (blocked / "inner").mkdir()
    blocked.chmod(0o000)
    monkeypatch.setattr(db, "GROUP_CONTAINER", blocked)
    try:
        with pytest.raises(db.ThingsDBPermissionError):
            db.find_database()
    finally:
        blocked.chmod(0o755)  # restore so tmp cleanup can remove it


def test_missing_container_is_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    monkeypatch.setattr(db, "GROUP_CONTAINER", tmp_path / "does-not-exist")
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()
