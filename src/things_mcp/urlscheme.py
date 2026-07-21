"""Pure builders for things:/// URLs. No I/O, no side effects."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_COMMA_KEYS = {"tags", "add-tags", "filter"}
_NEWLINE_KEYS = {"checklist-items", "titles", "to-dos"}

_AUTH_TOKEN_RE = re.compile(r"(auth-token=)[^&\s]*")


def redact_auth_token(text: str) -> str:
    """Replace any ``auth-token=...`` value with a redaction marker.

    The Things auth token is a persistent write credential for the user's task
    database. It must never be returned to the model or echoed into error
    messages/transcripts, so any string that may contain it is scrubbed first.
    """
    return _AUTH_TOKEN_RE.sub(r"\1<redacted>", text)


def _encode_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        sep = "," if key in _COMMA_KEYS else "\n" if key in _NEWLINE_KEYS else ","
        return sep.join(str(v) for v in value)
    return str(value)


def build_url(command: str, params: dict[str, Any]) -> str:
    """Build a things:/// URL. None values are omitted; '' is preserved (clears)."""
    parts = []
    for key, value in params.items():
        if value is None:
            continue
        encoded = _encode_value(key, value)
        parts.append(f"{quote(key, safe='')}={quote(encoded, safe='')}")
    query = "&".join(parts)
    return f"things:///{command}?{query}" if query else f"things:///{command}"


def add_todo_url(
    *,
    title: str | None = None,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    checklist_items: list[str] | None = None,
    list: str | None = None,
    list_id: str | None = None,
    heading: str | None = None,
) -> str:
    return build_url(
        "add",
        {
            "title": title,
            "notes": notes,
            "when": when,
            "deadline": deadline,
            "tags": tags,
            "checklist-items": checklist_items,
            "list": list,
            "list-id": list_id,
            "heading": heading,
        },
    )


def add_project_url(
    *,
    title: str | None = None,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    area: str | None = None,
    area_id: str | None = None,
    todos: list[str] | None = None,
) -> str:
    return build_url(
        "add-project",
        {
            "title": title,
            "notes": notes,
            "when": when,
            "deadline": deadline,
            "tags": tags,
            "area": area,
            "area-id": area_id,
            "to-dos": todos,
        },
    )


def update_url(*, id: str, auth_token: str, command: str = "update", **fields: Any) -> str:
    params: dict[str, Any] = {"id": id, "auth-token": auth_token}
    params.update(fields)
    return build_url(command, params)


def show_url(*, id: str | None = None, query: str | None = None) -> str:
    return build_url("show", {"id": id, "query": query})
