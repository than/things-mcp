"""Read adapter: thin, typed wrappers over things.py (read-only SQLite)."""

from __future__ import annotations

from typing import Any

import things

from things_mcp import db


def _fp(filepath: str | None) -> str:
    return filepath if filepath is not None else str(db.find_database())


def list_inbox(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.inbox(filepath=_fp(filepath))


def list_today(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.today(filepath=_fp(filepath))


def list_upcoming(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.upcoming(filepath=_fp(filepath))


def list_anytime(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.anytime(filepath=_fp(filepath))


def list_someday(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.someday(filepath=_fp(filepath))


def list_logbook(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.logbook(filepath=_fp(filepath))


def list_todos(
    project: str | None = None,
    area: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    deadline: str | None = None,
    filepath: str | None = None,
) -> list[dict[str, Any]]:
    return things.todos(
        project=project,
        area=area,
        tag=tag,
        status=status,
        deadline=deadline,
        filepath=_fp(filepath),
    )


def list_projects(
    area: str | None = None, filepath: str | None = None
) -> list[dict[str, Any]]:
    return things.projects(area=area, filepath=_fp(filepath))


def list_areas(filepath: str | None = None) -> list[dict[str, Any]]:
    return things.areas(filepath=_fp(filepath))


def list_tags(filepath: str | None = None) -> list[str]:
    return things.tags(titles_only=True, filepath=_fp(filepath))


def search(query: str, filepath: str | None = None) -> list[dict[str, Any]]:
    return things.search(query, filepath=_fp(filepath))


def get_item(uuid: str, filepath: str | None = None) -> dict[str, Any] | None:
    return things.get(uuid, None, filepath=_fp(filepath))


def list_recent(offset: str, filepath: str | None = None) -> list[dict[str, Any]]:
    return things.last(offset, filepath=_fp(filepath))
