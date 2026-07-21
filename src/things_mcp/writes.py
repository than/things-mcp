"""Write adapter: build a things:/// URL, execute it, best-effort read back."""

from __future__ import annotations

import time
from typing import Any, Callable

import things

from things_mcp import db, reads, runner, urlscheme

_TOKEN_CACHE: dict[str, str] = {}

# Things handles the URL asynchronously, so a newly created item may not appear
# in a read the instant `open` returns. Poll a few times before giving up.
_READBACK_ATTEMPTS = 3
_READBACK_DELAY = 0.25

_URLS_DISABLED_HINT = (
    "Could not read the Things auth token. Enable it in Things: "
    "Settings → General → Enable Things URLs → Manage, then try again."
)


class ThingsAuthError(db.ThingsError):
    """The Things URL-scheme auth token is unavailable."""


def get_token() -> str:
    if "token" in _TOKEN_CACHE:
        return _TOKEN_CACHE["token"]
    tok = things.token(filepath=str(db.find_database()))
    if not tok:
        raise ThingsAuthError(_URLS_DISABLED_HINT)
    _TOKEN_CACHE["token"] = tok
    return tok


def _snapshot_uuids(lister: Callable[[], list[dict[str, Any]]]) -> set[str] | None:
    try:
        return {item.get("uuid") for item in lister()}
    except Exception:
        return None


def _confirm_new(
    title: str,
    before: set[str] | None,
    lister: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Return the newly-created item, or None if it cannot be uniquely confirmed.

    Matches only an item whose uuid did NOT exist before the write (so a
    pre-existing same-title todo is never mistaken for the new one, and a write
    that silently failed is not falsely confirmed). If more than one new item
    shares the title, the result is ambiguous and we report None rather than
    guessing.
    """
    if before is None:
        return None
    for attempt in range(_READBACK_ATTEMPTS):
        try:
            after = lister()
        except Exception:
            return None
        fresh = [
            item
            for item in after
            if item.get("uuid") not in before and item.get("title") == title
        ]
        if len(fresh) == 1:
            return fresh[0]
        if len(fresh) > 1:
            return None  # ambiguous — do not guess
        if attempt < _READBACK_ATTEMPTS - 1:
            time.sleep(_READBACK_DELAY)
    return None


def add_todo(
    title: str,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    checklist_items: list[str] | None = None,
    list: str | None = None,
    heading: str | None = None,
) -> dict[str, Any]:
    url = urlscheme.add_todo_url(
        title=title,
        notes=notes,
        when=when,
        deadline=deadline,
        tags=tags,
        checklist_items=checklist_items,
        list=list,
        heading=heading,
    )
    # Snapshot across ALL incomplete to-dos (covers inbox and list/heading
    # targets alike) so the read-back works regardless of destination.
    before = _snapshot_uuids(reads.list_todos)
    runner.run_url(url)
    match = _confirm_new(title, before, reads.list_todos)
    return {"ok": True, "url": url, "match": match}


def add_project(
    title: str,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    area: str | None = None,
    todos: list[str] | None = None,
) -> dict[str, Any]:
    url = urlscheme.add_project_url(
        title=title,
        notes=notes,
        when=when,
        deadline=deadline,
        tags=tags,
        area=area,
        todos=todos,
    )
    before = _snapshot_uuids(reads.list_projects)
    runner.run_url(url)
    match = _confirm_new(title, before, reads.list_projects)
    return {"ok": True, "url": url, "match": match}


def _update(command: str, id: str, fields: dict[str, Any]) -> dict[str, Any]:
    url = urlscheme.update_url(id=id, auth_token=get_token(), command=command, **fields)
    runner.run_url(url)
    # Never return the token-bearing URL to the caller/model — redact it.
    return {"ok": True, "url": urlscheme.redact_auth_token(url)}


def update_todo(id: str, **fields: Any) -> dict[str, Any]:
    return _update("update", id, fields)


def update_project(id: str, **fields: Any) -> dict[str, Any]:
    return _update("update-project", id, fields)


def complete_todo(id: str) -> dict[str, Any]:
    return _update("update", id, {"completed": True})


def cancel_todo(id: str) -> dict[str, Any]:
    return _update("update", id, {"canceled": True})
