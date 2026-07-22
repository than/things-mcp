"""Read-backend dispatcher: SQLite (fast, needs Full Disk Access) or AppleScript
(no FDA, needs Things running).

Selection order:
1. ``THINGS_MCP_BACKEND`` env var: ``sqlite`` | ``applescript`` | ``auto`` (default).
2. auto: use SQLite if the database is reachable (FDA granted), else AppleScript.

The chosen module is cached for the process. Both backends expose the same read
functions, so callers use this module exactly like ``reads``.
"""

from __future__ import annotations

import os
from typing import Any

from things_mcp import applescript, db
from things_mcp import reads as sqlite_reads

_CACHE: dict[str, Any] = {}

BACKEND_ENV = "THINGS_MCP_BACKEND"


def active_backend() -> str:
    """Return the name of the backend that will be used: 'sqlite' or 'applescript'."""
    return "sqlite" if _choose() is sqlite_reads else "applescript"


def _choose():
    override = os.environ.get(BACKEND_ENV, "auto").strip().lower()
    if override == "sqlite":
        return sqlite_reads
    if override == "applescript":
        return applescript
    if "mod" in _CACHE:
        return _CACHE["mod"]
    try:
        db.find_database()
        mod = sqlite_reads
    except db.ThingsError:
        mod = applescript
    _CACHE["mod"] = mod
    return mod


def reset_cache() -> None:
    _CACHE.clear()


def list_inbox() -> list[dict[str, Any]]:
    return _choose().list_inbox()


def list_today() -> list[dict[str, Any]]:
    return _choose().list_today()


def list_upcoming() -> list[dict[str, Any]]:
    return _choose().list_upcoming()


def list_anytime() -> list[dict[str, Any]]:
    return _choose().list_anytime()


def list_someday() -> list[dict[str, Any]]:
    return _choose().list_someday()


def list_logbook() -> list[dict[str, Any]]:
    return _choose().list_logbook()


def list_todos(
    project: str | None = None,
    area: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    deadline: str | None = None,
) -> list[dict[str, Any]]:
    return _choose().list_todos(
        project=project, area=area, tag=tag, status=status, deadline=deadline
    )


def list_projects(area: str | None = None) -> list[dict[str, Any]]:
    return _choose().list_projects(area=area)


def list_areas() -> list[dict[str, Any]]:
    return _choose().list_areas()


def list_tags() -> list[str]:
    return _choose().list_tags()


def search(query: str) -> list[dict[str, Any]]:
    return _choose().search(query)


def get_item(uuid: str) -> dict[str, Any] | None:
    return _choose().get_item(uuid)


def list_recent(offset: str) -> list[dict[str, Any]]:
    return _choose().list_recent(offset)
