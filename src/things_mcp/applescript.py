"""AppleScript read backend — no Full Disk Access required.

Reads Things data by scripting the app via Apple Events (osascript) instead of
opening the SQLite database. This only needs macOS *Automation* permission
(auto-prompted on first use), not Full Disk Access. Trade-offs vs. the SQLite
backend: Things must be running, it is slower (and can stall briefly while
Things Cloud is syncing), and a few fields (e.g. checklist items, per-item
project/area names) are not available.

Performance note: properties are fetched *vectorized* — one Apple Event returns
all ids, another all names, etc. — instead of per-item, which is orders of
magnitude faster. The incomplete-to-do view aggregates the built-in lists rather
than scanning the whole database (which includes the Logbook).

Output dicts are shaped to resemble things.py's so the server formats results
uniformly regardless of backend.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from things_mcp import db

# Field/record separators — control chars that will not appear in task text.
_US = "\x1f"
_RS = "\x1e"

_UUID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

_STATUS_MAP = {"open": "incomplete", "completed": "completed", "canceled": "canceled"}
_STATUS_TO_AS = {"incomplete": "open", "completed": "completed", "canceled": "canceled"}

# Built-in lists whose union is every incomplete to-do (no Logbook scan).
_OPEN_LISTS = ["Inbox", "Today", "Anytime", "Upcoming", "Someday"]

_AUTOMATION_HINT = (
    "Could not control Things via AppleScript. Make sure Things is running, then "
    "allow the Automation prompt (System Settings → Privacy & Security → "
    "Automation → enable Things for this app)."
)


class AppleScriptError(db.ThingsError):
    """Scripting Things via AppleScript failed."""


# ISO-date helpers + separators, shared by the row-emitting script.
_PRELUDE = """
on isoDate(d)
\tif d is missing value then return ""
\treturn (my pad(year of d, 4)) & "-" & (my pad((month of d as integer), 2)) & "-" & (my pad(day of d, 2))
end isoDate
on pad(n, w)
\tset s to (n as integer) as text
\trepeat while (length of s) < w
\t\tset s to "0" & s
\tend repeat
\treturn s
end pad
set US to (ASCII character 31)
set RS to (ASCII character 30)
"""

# Vectorized fetch: one Apple Event per property, then rows assembled locally.
# The `as list` coercions and the row loop run OUTSIDE the `tell` block on
# purpose — inside a Things `tell`, `list` names Things' list class (Inbox/
# Today/…), so `as list` there coerces to the wrong type and fails. 8 fields:
# id, name, status, notes, deadline, start, tags, created.
_ROWS_TMPL = (
    _PRELUDE
    + """
with timeout of 120 seconds
\ttell application "Things3"
\t\tset ids to id of ({source})
\t\tset nms to name of ({source})
\t\tset sts to status of ({source})
\t\tset nts to notes of ({source})
\t\tset dds to due date of ({source})
\t\tset ads to activation date of ({source})
\t\tset tgs to tag names of ({source})
\t\tset cds to creation date of ({source})
\tend tell
end timeout
set ids to ids as list
set nms to nms as list
set sts to sts as list
set nts to nts as list
set dds to dds as list
set ads to ads as list
set tgs to tgs as list
set cds to cds as list
set out to ""
repeat with i from 1 to (count of ids)
\tset out to out & (item i of ids) & US & (item i of nms) & US & ((item i of sts) as text) & US & (item i of nts) & US & (my isoDate(item i of dds)) & US & (my isoDate(item i of ads)) & US & (item i of tgs) & US & (my isoDate(item i of cds)) & RS
end repeat
return out
"""
)

_AREAS_SCRIPT = (
    _PRELUDE
    + """
with timeout of 120 seconds
\ttell application "Things3"
\t\tset ids to id of areas
\t\tset nms to name of areas
\tend tell
end timeout
set ids to ids as list
set nms to nms as list
set out to ""
repeat with i from 1 to (count of ids)
\tset out to out & (item i of ids) & US & (item i of nms) & RS
end repeat
return out
"""
)

_TAGS_SCRIPT = """
with timeout of 120 seconds
\ttell application "Things3"
\t\tset nms to name of tags
\tend tell
end timeout
set nms to nms as list
set RS to (ASCII character 30)
set out to ""
repeat with i from 1 to (count of nms)
\tset out to out & (item i of nms) & RS
end repeat
return out
"""


def _run(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:  # osascript missing → not macOS
        raise AppleScriptError(
            "The macOS `osascript` command was not found; this server runs on macOS only."
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise AppleScriptError(f"{_AUTOMATION_HINT}\n\n(osascript: {stderr})")
    return result.stdout


def available() -> bool:
    """True if Things can be scripted right now (running + automation allowed)."""
    try:
        out = _run('tell application "Things3" to return version')
        return bool(out.strip())
    except AppleScriptError:
        return False


def _tags_to_list(raw: str) -> list[str]:
    raw = raw.strip()
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


def _row_to_todo(fields: list[str]) -> dict[str, Any]:
    return {
        "uuid": fields[0],
        "type": "to-do",
        "title": fields[1],
        "status": _STATUS_MAP.get(fields[2], fields[2]),
        "notes": fields[3],
        "deadline": fields[4] or None,
        "start": fields[5] or None,
        "tags": _tags_to_list(fields[6]),
        "created": fields[7] or None,
    }


def _row_to_project(fields: list[str]) -> dict[str, Any]:
    item = _row_to_todo(fields)
    item["type"] = "project"
    return item


def _parse(raw: str, mapper, width: int) -> list[dict[str, Any]]:
    items = []
    # osascript appends a trailing newline; strip it so it is not parsed as an
    # empty phantom record.
    for record in raw.rstrip("\n").split(_RS):
        if not record.strip():
            continue
        fields = record.split(_US)
        if len(fields) < width:
            fields = fields + [""] * (width - len(fields))
        items.append(mapper(fields))
    return items


def _query_todos(source: str) -> list[dict[str, Any]]:
    return _parse(_run(_ROWS_TMPL.format(source=source)), _row_to_todo, 8)


def _query_projects(source: str) -> list[dict[str, Any]]:
    return _parse(_run(_ROWS_TMPL.format(source=source)), _row_to_project, 8)


def _dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        u = it.get("uuid")
        if u in seen:
            continue
        seen.add(u)
        out.append(it)
    return out


def _all_open_todos() -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for name in _OPEN_LISTS:
        collected.extend(_query_todos(f'to dos of list "{name}"'))
    return _dedup(collected)


# ---- Public read API (mirrors reads.py, minus filepath) ----
def list_inbox() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Inbox"')


def list_today() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Today"')


def list_upcoming() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Upcoming"')


def list_anytime() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Anytime"')


def list_someday() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Someday"')


def list_logbook() -> list[dict[str, Any]]:
    return _query_todos('to dos of list "Logbook"')


def list_todos(
    project: str | None = None,
    area: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    deadline: str | None = None,
) -> list[dict[str, Any]]:
    # project/area filtering is not supported on this backend.
    if status is None or status == "incomplete":
        todos = _all_open_todos()
    else:
        wanted = _STATUS_MAP.get(_STATUS_TO_AS.get(status, status), status)
        todos = [t for t in _query_todos('to dos of list "Logbook"') if t["status"] == wanted]
    if tag is not None:
        todos = [t for t in todos if tag in t.get("tags", [])]
    if deadline is not None:
        todos = [t for t in todos if t.get("deadline") == deadline]
    return todos


def list_projects(area: str | None = None) -> list[dict[str, Any]]:
    # area filtering is not supported on this backend.
    return _query_projects("projects")


def list_areas() -> list[dict[str, Any]]:
    items = []
    for record in _run(_AREAS_SCRIPT).rstrip("\n").split(_RS):
        if not record.strip():
            continue
        fields = record.split(_US)
        if len(fields) < 2:
            continue
        items.append({"uuid": fields[0], "type": "area", "title": fields[1]})
    return items


def list_tags() -> list[str]:
    raw = _run(_TAGS_SCRIPT)
    return [t for t in (x.strip() for x in raw.rstrip("\n").split(_RS)) if t]


def search(query: str) -> list[dict[str, Any]]:
    # Searches incomplete to-dos (fast). Logbook is excluded to avoid scanning
    # the whole database.
    q = query.lower()
    return [
        t
        for t in _all_open_todos()
        if q in (t.get("title") or "").lower() or q in (t.get("notes") or "").lower()
    ]


def list_recent(offset: str) -> list[dict[str, Any]]:
    # A `whose creation date > ...` scan iterates the entire database (incl. the
    # Logbook) and is very slow. Instead filter the fast incomplete-list
    # aggregate by creation date. Trade-off on this backend: recently *completed*
    # items are not included.
    import datetime

    days = _offset_to_days(offset)
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    todos = [t for t in _all_open_todos() if (t.get("created") or "") >= cutoff]
    todos.sort(key=lambda t: t.get("created") or "", reverse=True)
    return todos


def get_item(uuid: str) -> dict[str, Any] | None:
    if not _UUID_RE.match(uuid):
        raise AppleScriptError(f"Invalid item id: {uuid!r}")
    script = (
        _PRELUDE
        + f"""
tell application "Things3"
\tset theID to "{uuid}"
\ttry
\t\tset t to to do id theID
\t\treturn "to-do" & US & (id of t) & US & (name of t) & US & (status of t as text) & US & (notes of t) & US & (my isoDate(due date of t)) & US & (my isoDate(activation date of t)) & US & (tag names of t) & US & (my isoDate(creation date of t))
\tend try
\ttry
\t\tset p to project id theID
\t\treturn "project" & US & (id of p) & US & (name of p) & US & (status of p as text) & US & (notes of p) & US & (my isoDate(due date of p)) & US & (my isoDate(activation date of p)) & US & (tag names of p) & US & (my isoDate(creation date of p))
\tend try
\treturn ""
end tell
"""
    )
    raw = _run(script).strip("\n")
    if not raw:
        return None
    fields = raw.split(_US)
    kind = fields[0]
    body = fields[1:]
    if len(body) < 8:
        body = body + [""] * (8 - len(body))
    if kind == "project":
        return _row_to_project(body)
    return _row_to_todo(body)


def _offset_to_days(offset: str) -> int:
    """Convert an offset like '3d'/'2w'/'1y' to a number of days."""
    m = re.fullmatch(r"\s*(\d+)\s*([dwy])\s*", offset)
    if not m:
        raise ValueError(f"Invalid offset {offset!r}; expected like '3d', '2w', '1y'.")
    return int(m.group(1)) * {"d": 1, "w": 7, "y": 365}[m.group(2)]
