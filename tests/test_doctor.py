import pathlib

from things_mcp import doctor, db, writes


def test_all_pass(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    assert [c["ok"] for c in checks] == [True, True, True]


def test_permission_failure_reported(monkeypatch):
    def boom():
        raise db.ThingsDBPermissionError("Full Disk Access needed")

    monkeypatch.setattr(db, "find_database", boom)
    checks = doctor.run_checks()
    found = next(c for c in checks if c["name"] == "database_found")
    assert found["ok"] is False
    assert "Full Disk Access" in found["remediation"] or "FDA" in found["remediation"]


def test_token_failure_reported(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))

    def no_token():
        raise writes.ThingsAuthError("enable URLs")

    monkeypatch.setattr(writes, "get_token", no_token)
    checks = doctor.run_checks()
    urls = next(c for c in checks if c["name"] == "things_urls_enabled")
    assert urls["ok"] is False


def test_not_found_skips_token_check(monkeypatch):
    def boom():
        raise db.ThingsDBNotFoundError("no db")

    monkeypatch.setattr(db, "find_database", boom)
    checks = doctor.run_checks()
    urls = next(c for c in checks if c["name"] == "things_urls_enabled")
    assert urls["ok"] is False
    assert "database" in urls["detail"].lower()
