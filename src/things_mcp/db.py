"""Locate the Things 3 SQLite database with TCC-aware error reporting."""

from __future__ import annotations

import os
import pathlib
from typing import Iterator

THINGSDB_ENV = "THINGSDB"

GROUP_CONTAINER = (
    pathlib.Path.home()
    / "Library"
    / "Group Containers"
    / "JLMPQHK86H.com.culturedcode.ThingsMac"
)

_FDA_HINT = (
    "macOS is blocking access to the Things database (Full Disk Access / TCC). "
    "Grant Full Disk Access to the app that launches this server "
    "(your terminal app for Claude Code, or Claude.app for Claude Desktop): "
    "System Settings → Privacy & Security → Full Disk Access → enable it, "
    "then fully quit and reopen that app."
)

_NOT_FOUND_HINT = (
    "Could not find the Things database. Make sure Things 3 is installed and has "
    "been opened at least once so its database exists. If it lives in a custom "
    f"location, set the {THINGSDB_ENV} environment variable to the main.sqlite path."
)


class ThingsError(Exception):
    """Base error for things-mcp."""


class ThingsDBNotFoundError(ThingsError):
    """The Things database could not be located."""


class ThingsDBPermissionError(ThingsError):
    """macOS TCC denied access to the Things database."""


def _iter_candidate_dbs() -> Iterator[pathlib.Path]:
    """Yield main.sqlite candidates under the group container.

    Implemented as a manual scandir walk rather than ``Path.glob`` because
    ``glob`` silently swallows ``PermissionError`` (returning no matches),
    which would misreport a TCC/Full-Disk-Access denial as "database not
    found". A raised ``PermissionError`` here propagates to the caller so it
    can be surfaced as :class:`ThingsDBPermissionError`.
    """
    try:
        stack = [GROUP_CONTAINER]
    except OSError:  # pragma: no cover - defensive
        return
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except FileNotFoundError:
            # Directory vanished or the container doesn't exist yet.
            continue
        # PermissionError intentionally NOT caught here: let it propagate.
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                stack.append(pathlib.Path(entry.path))
            elif entry.name == "main.sqlite":
                yield pathlib.Path(entry.path)


def _readable(path: pathlib.Path) -> bool:
    try:
        with open(path, "rb"):
            return True
    except PermissionError:
        raise
    except OSError:
        return False


def find_database() -> pathlib.Path:
    """Return a readable Things DB path, or raise a precise error.

    Order: THINGSDB env override, then glob the group container.
    Distinguishes PermissionError (TCC) from not-found.
    """
    override = os.environ.get(THINGSDB_ENV)
    if override:
        path = pathlib.Path(override).expanduser()
        try:
            if path.is_file() and _readable(path):
                return path
        except PermissionError as exc:
            raise ThingsDBPermissionError(_FDA_HINT) from exc
        raise ThingsDBNotFoundError(
            f"{THINGSDB_ENV} is set to '{path}' but no readable database is there."
        )

    try:
        candidates = sorted(_iter_candidate_dbs(), key=lambda p: len(p.parts))
    except PermissionError as exc:
        raise ThingsDBPermissionError(_FDA_HINT) from exc

    for path in candidates:
        try:
            if _readable(path):
                return path
        except PermissionError as exc:
            raise ThingsDBPermissionError(_FDA_HINT) from exc

    raise ThingsDBNotFoundError(_NOT_FOUND_HINT)
