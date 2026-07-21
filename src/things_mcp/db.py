"""Locate the Things 3 SQLite database with TCC-aware error reporting."""

from __future__ import annotations

import os
import pathlib

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


def _scan_candidates() -> tuple[list[pathlib.Path], bool]:
    """Return ``(candidates, permission_denied)`` under the group container.

    Implemented as a manual scandir walk rather than ``Path.glob`` because
    ``glob`` silently swallows ``PermissionError`` (returning no matches),
    which would misreport a TCC/Full-Disk-Access denial as "database not
    found".

    A ``PermissionError`` on any directory sets ``permission_denied=True`` but
    does NOT abort the walk: if a readable database exists elsewhere we want to
    use it (a single unreadable sibling should not force a misleading Full Disk
    Access message). ``follow_symlinks=False`` avoids symlink recursion loops.
    """
    candidates: list[pathlib.Path] = []
    permission_denied = False
    stack = [GROUP_CONTAINER]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except FileNotFoundError:
            # Directory vanished or the container doesn't exist yet.
            continue
        except PermissionError:
            # TCC or POSIX denial on this directory; remember it and move on.
            permission_denied = True
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                stack.append(pathlib.Path(entry.path))
            elif entry.name == "main.sqlite":
                candidates.append(pathlib.Path(entry.path))
    return candidates, permission_denied


def _rank_candidate(path: pathlib.Path) -> tuple[bool, float]:
    """Sort key (higher is better): current ``ThingsData-*`` layout, then mtime.

    Things >= 3.15.16 stores the live DB under ``ThingsData-XXXX/...``; older
    versions used a flat ``Things Database.thingsdatabase/...`` path. When both
    linger, the ``ThingsData-*`` one is authoritative — mirroring things.py's
    own resolver. Among equals, the most recently modified wins.
    """
    is_thingsdata = any(part.startswith("ThingsData-") for part in path.parts)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (is_thingsdata, mtime)


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

    candidates, permission_denied = _scan_candidates()
    # Best (current-layout, newest) first.
    candidates.sort(key=_rank_candidate, reverse=True)

    for path in candidates:
        try:
            if _readable(path):
                return path
        except PermissionError:
            permission_denied = True
            continue

    # No readable database. Distinguish a TCC/permission wall from a genuine
    # absence so the user gets the right remediation.
    if permission_denied:
        raise ThingsDBPermissionError(_FDA_HINT)
    raise ThingsDBNotFoundError(_NOT_FOUND_HINT)
