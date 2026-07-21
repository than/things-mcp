"""Preflight diagnostics with exact remediation for each failure."""

from __future__ import annotations

from typing import Any

from things_mcp import db, writes


def run_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1 + 2: database found & readable (find_database validates readability).
    path = None
    try:
        path = db.find_database()
        checks.append(
            {"name": "database_found", "ok": True, "detail": str(path), "remediation": None}
        )
        checks.append(
            {
                "name": "database_readable",
                "ok": True,
                "detail": "read access OK",
                "remediation": None,
            }
        )
    except db.ThingsDBPermissionError as exc:
        checks.append(
            {
                "name": "database_found",
                "ok": False,
                "detail": "permission denied",
                "remediation": str(exc),
            }
        )
        checks.append(
            {
                "name": "database_readable",
                "ok": False,
                "detail": "blocked by macOS TCC",
                "remediation": str(exc),
            }
        )
    except db.ThingsDBNotFoundError as exc:
        checks.append(
            {
                "name": "database_found",
                "ok": False,
                "detail": "not found",
                "remediation": str(exc),
            }
        )
        checks.append(
            {
                "name": "database_readable",
                "ok": False,
                "detail": "no database to read",
                "remediation": str(exc),
            }
        )

    # 3: Things URLs enabled (token present).
    if path is None:
        checks.append(
            {
                "name": "things_urls_enabled",
                "ok": False,
                "detail": "skipped (no database)",
                "remediation": "Resolve the database check first.",
            }
        )
        return checks
    try:
        writes.get_token()
        checks.append(
            {
                "name": "things_urls_enabled",
                "ok": True,
                "detail": "auth token present",
                "remediation": None,
            }
        )
    except writes.ThingsAuthError as exc:
        checks.append(
            {
                "name": "things_urls_enabled",
                "ok": False,
                "detail": "no auth token",
                "remediation": str(exc),
            }
        )
    return checks
