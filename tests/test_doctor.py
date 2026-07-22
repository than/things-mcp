import pathlib

import pytest

from things_mcp import doctor, db, writes, applescript, read_backend


def _named(checks, name):
    return next(c for c in checks if c["name"] == name)


def test_sqlite_backend_all_pass(monkeypatch, fixture_db):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "sqlite")
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    assert all(c["ok"] for c in checks)
    assert _named(checks, "read_backend")["detail"].startswith("sqlite")
    assert _named(checks, "database_readable")["ok"] is True


def test_sqlite_permission_failure_reports_fda(monkeypatch):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "sqlite")

    def boom():
        raise db.ThingsDBPermissionError("Full Disk Access needed")

    monkeypatch.setattr(db, "find_database", boom)
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    found = _named(checks, "database_found")
    assert found["ok"] is False
    assert "Full Disk Access" in found["remediation"]


def test_applescript_backend_available(monkeypatch):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "applescript")
    monkeypatch.setattr(applescript, "available", lambda: True)
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    assert _named(checks, "read_backend")["detail"].startswith("applescript")
    assert _named(checks, "applescript_available")["ok"] is True


def test_applescript_backend_unavailable(monkeypatch):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "applescript")
    monkeypatch.setattr(applescript, "available", lambda: False)
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    avail = _named(checks, "applescript_available")
    assert avail["ok"] is False
    assert "Automation" in avail["remediation"]


def test_token_failure_reported(monkeypatch, fixture_db):
    monkeypatch.setenv(read_backend.BACKEND_ENV, "sqlite")
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))

    def no_token():
        raise writes.ThingsAuthError("enable URLs")

    monkeypatch.setattr(writes, "get_token", no_token)
    checks = doctor.run_checks()
    assert _named(checks, "things_urls_enabled")["ok"] is False
