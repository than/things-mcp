"""Preflight diagnostics with exact remediation for each failure."""

from __future__ import annotations

from typing import Any

from things_mcp import applescript, db, read_backend, writes


def run_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    backend = read_backend.active_backend()
    checks.append(
        {
            "name": "read_backend",
            "ok": True,
            "detail": backend
            + (
                " (fast; needs Full Disk Access)"
                if backend == "sqlite"
                else " (no Full Disk Access needed; needs Things running)"
            ),
            "remediation": None,
        }
    )

    if backend == "sqlite":
        checks.extend(_sqlite_checks())
    else:
        checks.append(_applescript_check())

    checks.append(_token_check())
    return checks


def _sqlite_checks() -> list[dict[str, Any]]:
    try:
        path = db.find_database()
        return [
            {"name": "database_found", "ok": True, "detail": str(path), "remediation": None},
            {
                "name": "database_readable",
                "ok": True,
                "detail": "read access OK",
                "remediation": None,
            },
        ]
    except db.ThingsDBPermissionError as exc:
        return [
            {
                "name": "database_found",
                "ok": False,
                "detail": "permission denied",
                "remediation": str(exc),
            },
            {
                "name": "database_readable",
                "ok": False,
                "detail": "blocked by macOS TCC",
                "remediation": str(exc),
            },
        ]
    except db.ThingsDBNotFoundError as exc:
        return [
            {"name": "database_found", "ok": False, "detail": "not found", "remediation": str(exc)},
            {
                "name": "database_readable",
                "ok": False,
                "detail": "no database to read",
                "remediation": str(exc),
            },
        ]


def _applescript_check() -> dict[str, Any]:
    if applescript.available():
        return {
            "name": "applescript_available",
            "ok": True,
            "detail": "Things is scriptable",
            "remediation": None,
        }
    return {
        "name": "applescript_available",
        "ok": False,
        "detail": "cannot control Things",
        "remediation": (
            "Open Things, then allow the Automation prompt "
            "(System Settings → Privacy & Security → Automation)."
        ),
    }


def _token_check() -> dict[str, Any]:
    try:
        writes.get_token()
        return {
            "name": "things_urls_enabled",
            "ok": True,
            "detail": "auth token present",
            "remediation": None,
        }
    except writes.ThingsAuthError as exc:
        return {
            "name": "things_urls_enabled",
            "ok": False,
            "detail": "no auth token",
            "remediation": str(exc),
        }
    except db.ThingsError as exc:
        # e.g. token read needs the DB but FDA is denied and no env token set.
        return {
            "name": "things_urls_enabled",
            "ok": False,
            "detail": "token unavailable",
            "remediation": str(exc),
        }
