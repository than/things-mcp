"""Write adapter: build a things:/// URL, execute it, best-effort read back."""

from __future__ import annotations

from typing import Any

import things

from things_mcp import db, reads, runner, urlscheme

_TOKEN_CACHE: dict[str, str] = {}

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


def _match_recent(title: str, listing: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in listing:
        if item.get("title") == title:
            return item
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
    runner.run_url(url)
    # Best-effort read-back: newly added todos without a list land in the inbox.
    match = None
    try:
        match = _match_recent(title, reads.list_inbox())
    except Exception:
        match = None
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
    runner.run_url(url)
    match = None
    try:
        match = _match_recent(title, reads.list_projects())
    except Exception:
        match = None
    return {"ok": True, "url": url, "match": match}


def _update(command: str, id: str, fields: dict[str, Any]) -> dict[str, Any]:
    url = urlscheme.update_url(id=id, auth_token=get_token(), command=command, **fields)
    runner.run_url(url)
    return {"ok": True, "url": url}


def update_todo(id: str, **fields: Any) -> dict[str, Any]:
    return _update("update", id, fields)


def update_project(id: str, **fields: Any) -> dict[str, Any]:
    return _update("update-project", id, fields)


def complete_todo(id: str) -> dict[str, Any]:
    return _update("update", id, {"completed": True})


def cancel_todo(id: str) -> dict[str, Any]:
    return _update("update", id, {"canceled": True})
