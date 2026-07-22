"""FastMCP server exposing Things read/write tools."""

from __future__ import annotations

import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from things_mcp import db, doctor, runner, writes
from things_mcp import read_backend as reads

mcp = FastMCP("things")


def _safe(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (db.ThingsError, runner.RunnerError, ValueError) as exc:
            # ValueError covers things.py's argument validation (unknown status,
            # bad offset/deadline) so those surface as a friendly error dict
            # instead of an opaque tool exception.
            return {"error": str(exc)}

    return wrapper


# ---- Reads ----
@mcp.tool()
@_safe
def list_inbox() -> Any:
    """To-dos in the Inbox."""
    return reads.list_inbox()


@mcp.tool()
@_safe
def list_today() -> Any:
    """To-dos scheduled for Today (plus overdue)."""
    return reads.list_today()


@mcp.tool()
@_safe
def list_upcoming() -> Any:
    """Scheduled future to-dos (Upcoming)."""
    return reads.list_upcoming()


@mcp.tool()
@_safe
def list_anytime() -> Any:
    """To-dos in Anytime."""
    return reads.list_anytime()


@mcp.tool()
@_safe
def list_someday() -> Any:
    """To-dos in Someday."""
    return reads.list_someday()


@mcp.tool()
@_safe
def list_logbook() -> Any:
    """Completed/canceled to-dos (Logbook)."""
    return reads.list_logbook()


@mcp.tool()
@_safe
def list_todos(
    project: str | None = None,
    area: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    deadline: str | None = None,
) -> Any:
    """To-dos filtered by project/area/tag/status/deadline (all optional)."""
    return reads.list_todos(
        project=project, area=area, tag=tag, status=status, deadline=deadline
    )


@mcp.tool()
@_safe
def list_projects(area: str | None = None) -> Any:
    """Projects, optionally filtered by area uuid."""
    return reads.list_projects(area=area)


@mcp.tool()
@_safe
def list_areas() -> Any:
    """All areas."""
    return reads.list_areas()


@mcp.tool()
@_safe
def list_tags() -> Any:
    """All tag titles."""
    return reads.list_tags()


@mcp.tool()
@_safe
def search(query: str) -> Any:
    """Search to-dos/projects by title and notes."""
    return reads.search(query)


@mcp.tool()
@_safe
def get_item(uuid: str) -> Any:
    """Fetch a single to-do/project/area by uuid (with checklist items)."""
    return reads.get_item(uuid)


@mcp.tool()
@_safe
def list_recent(offset: str) -> Any:
    """Items created within an offset like '3d', '1w', '1y'."""
    return reads.list_recent(offset)


# ---- Writes ----
@mcp.tool()
@_safe
def add_todo(
    title: str,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    checklist_items: list[str] | None = None,
    list: str | None = None,
    heading: str | None = None,
) -> Any:
    """Create a to-do. `when`: today/tomorrow/evening/anytime/someday/yyyy-mm-dd."""
    return writes.add_todo(
        title,
        notes=notes,
        when=when,
        deadline=deadline,
        tags=tags,
        checklist_items=checklist_items,
        list=list,
        heading=heading,
    )


@mcp.tool()
@_safe
def add_project(
    title: str,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    area: str | None = None,
    todos: list[str] | None = None,
) -> Any:
    """Create a project, optionally pre-filled with to-dos."""
    return writes.add_project(
        title,
        notes=notes,
        when=when,
        deadline=deadline,
        tags=tags,
        area=area,
        todos=todos,
    )


@mcp.tool()
@_safe
def update_todo(
    id: str,
    title: str | None = None,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    add_tags: list[str] | None = None,
    completed: bool | None = None,
    canceled: bool | None = None,
) -> Any:
    """Update an existing to-do by id (requires Things URLs enabled)."""
    fields = {
        "title": title,
        "notes": notes,
        "when": when,
        "deadline": deadline,
        "tags": tags,
        "add-tags": add_tags,
        "completed": completed,
        "canceled": canceled,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return writes.update_todo(id, **fields)


@mcp.tool()
@_safe
def update_project(
    id: str,
    title: str | None = None,
    notes: str | None = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    completed: bool | None = None,
    canceled: bool | None = None,
) -> Any:
    """Update an existing project by id (requires Things URLs enabled)."""
    fields = {
        "title": title,
        "notes": notes,
        "when": when,
        "deadline": deadline,
        "tags": tags,
        "completed": completed,
        "canceled": canceled,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return writes.update_project(id, **fields)


@mcp.tool()
@_safe
def complete_todo(id: str) -> Any:
    """Mark a to-do complete."""
    return writes.complete_todo(id)


@mcp.tool()
@_safe
def cancel_todo(id: str) -> Any:
    """Mark a to-do canceled."""
    return writes.cancel_todo(id)


# ---- Diagnostics ----
@mcp.tool(name="doctor")
@_safe
def doctor_check() -> Any:
    """Preflight: DB found? readable (Full Disk Access)? Things URLs enabled?"""
    return doctor.run_checks()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
