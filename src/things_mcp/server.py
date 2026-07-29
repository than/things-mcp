"""FastMCP server exposing Things read/write tools."""

from __future__ import annotations

import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from things_mcp import db, doctor, runner, writes
from things_mcp import read_backend as reads

INSTRUCTIONS = """\
Read and write the user's Things 3 task database on this Mac.

Reads come from the local Things database (via AppleScript, or direct SQLite when
Full Disk Access is granted) and return JSON. Writes go through the Things URL
scheme, so Things must be running and "Enable Things URLs" must be on
(Things > Settings > General).

Conventions:
- Items are identified by `uuid` (reads) / `id` (writes) — the same value.
- `when` accepts today, tomorrow, evening, anytime, someday, or yyyy-mm-dd.
- `deadline` is yyyy-mm-dd.
- Run `doctor` first if any tool reports a permissions or URL-scheme error.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
CREATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
MODIFY = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

mcp = FastMCP(
    "things",
    instructions=INSTRUCTIONS,
    website_url="https://github.com/than/things-mcp",
)


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
@mcp.tool(title="List Inbox", annotations=READ_ONLY)
@_safe
def list_inbox() -> Any:
    """List every to-do sitting in the Things Inbox — items captured but not yet
    filed into a project or area. Returns uuid, title, notes, tags, and dates."""
    return reads.list_inbox()


@mcp.tool(title="List Today", annotations=READ_ONLY)
@_safe
def list_today() -> Any:
    """List the to-dos on the Today list, including anything overdue that Things
    has rolled forward. This is the answer to "what am I working on today?"."""
    return reads.list_today()


@mcp.tool(title="List Upcoming", annotations=READ_ONLY)
@_safe
def list_upcoming() -> Any:
    """List to-dos scheduled for a future date (the Upcoming list), including
    repeating items' next occurrences."""
    return reads.list_upcoming()


@mcp.tool(title="List Anytime", annotations=READ_ONLY)
@_safe
def list_anytime() -> Any:
    """List to-dos in Anytime — active work with no scheduled date, i.e. the pool
    of things that could be pulled into Today."""
    return reads.list_anytime()


@mcp.tool(title="List Someday", annotations=READ_ONLY)
@_safe
def list_someday() -> Any:
    """List to-dos parked in Someday — deferred ideas the user is not committed
    to yet."""
    return reads.list_someday()


@mcp.tool(title="List Logbook", annotations=READ_ONLY)
@_safe
def list_logbook() -> Any:
    """List completed and canceled to-dos from the Logbook, newest first. Use
    this to report on what was finished over a period."""
    return reads.list_logbook()


@mcp.tool(title="List To-dos (filtered)", annotations=READ_ONLY)
@_safe
def list_todos(
    project: str | None = None,
    area: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    deadline: str | None = None,
) -> Any:
    """Query to-dos with any combination of filters. All arguments are optional;
    with none, returns all incomplete to-dos.

    Args:
        project: project uuid to restrict results to.
        area: area uuid to restrict results to.
        tag: tag title, e.g. "errand".
        status: "incomplete", "completed", or "canceled".
        deadline: yyyy-mm-dd; returns items due on or before that date.
    """
    return reads.list_todos(
        project=project, area=area, tag=tag, status=status, deadline=deadline
    )


@mcp.tool(title="List Projects", annotations=READ_ONLY)
@_safe
def list_projects(area: str | None = None) -> Any:
    """List all projects, optionally only those inside one area.

    Args:
        area: area uuid from list_areas.
    """
    return reads.list_projects(area=area)


@mcp.tool(title="List Areas", annotations=READ_ONLY)
@_safe
def list_areas() -> Any:
    """List all areas of responsibility (Work, Home, ...) with their uuids —
    the uuids other tools take as an `area` argument."""
    return reads.list_areas()


@mcp.tool(title="List Tags", annotations=READ_ONLY)
@_safe
def list_tags() -> Any:
    """List every tag title defined in Things. Use before tagging so new items
    reuse existing tags instead of creating near-duplicates."""
    return reads.list_tags()


@mcp.tool(title="Search Things", annotations=READ_ONLY)
@_safe
def search(query: str) -> Any:
    """Full-text search across to-do and project titles and notes.

    Args:
        query: substring to match, case-insensitive.
    """
    return reads.search(query)


@mcp.tool(title="Get Item", annotations=READ_ONLY)
@_safe
def get_item(uuid: str) -> Any:
    """Fetch one to-do, project, or area by uuid, including its checklist items
    and full notes — more detail than the list tools return.

    Args:
        uuid: id returned by any list or search tool.
    """
    return reads.get_item(uuid)


@mcp.tool(title="List Recently Created", annotations=READ_ONLY)
@_safe
def list_recent(offset: str) -> Any:
    """List items created within a recent time window.

    Args:
        offset: window like "3d", "1w", "6m", "1y".
    """
    return reads.list_recent(offset)


# ---- Writes ----
@mcp.tool(title="Add To-do", annotations=CREATE)
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
    """Create a new to-do in Things. Requires Things to be running with URLs
    enabled (run `doctor` if this fails).

    Args:
        title: the to-do's name. Required.
        notes: body text for the to-do.
        when: today, tomorrow, evening, anytime, someday, or yyyy-mm-dd.
        deadline: hard due date, yyyy-mm-dd.
        tags: tag titles to apply; unknown tags are ignored by Things.
        checklist_items: sub-steps to add inside the to-do.
        list: destination project or area, by title or uuid. Omit for Inbox.
        heading: heading within the destination project to file under.
    """
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


@mcp.tool(title="Add Project", annotations=CREATE)
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
    """Create a new project, optionally pre-filled with to-dos.

    Args:
        title: the project's name. Required.
        notes: body text for the project.
        when: today, tomorrow, evening, anytime, someday, or yyyy-mm-dd.
        deadline: hard due date, yyyy-mm-dd.
        tags: tag titles to apply.
        area: destination area, by title or uuid.
        todos: titles of to-dos to create inside the new project, in order.
    """
    return writes.add_project(
        title,
        notes=notes,
        when=when,
        deadline=deadline,
        tags=tags,
        area=area,
        todos=todos,
    )


@mcp.tool(title="Update To-do", annotations=MODIFY)
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
    """Change fields on an existing to-do. Only the arguments you pass are
    modified; everything else is left alone.

    Args:
        id: uuid of the to-do. Required.
        title: new name.
        notes: replaces the existing notes.
        when: today, tomorrow, evening, anytime, someday, or yyyy-mm-dd.
        deadline: hard due date, yyyy-mm-dd.
        tags: replaces all tags with this list.
        add_tags: appends these tags, keeping existing ones.
        completed: true marks it done.
        canceled: true marks it canceled.
    """
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


@mcp.tool(title="Update Project", annotations=MODIFY)
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
    """Change fields on an existing project. Only the arguments you pass are
    modified; everything else is left alone.

    Args:
        id: uuid of the project. Required.
        title: new name.
        notes: replaces the existing notes.
        when: today, tomorrow, evening, anytime, someday, or yyyy-mm-dd.
        deadline: hard due date, yyyy-mm-dd.
        tags: replaces all tags with this list.
        completed: true marks the project done.
        canceled: true marks the project canceled.
    """
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


@mcp.tool(title="Complete To-do", annotations=MODIFY)
@_safe
def complete_todo(id: str) -> Any:
    """Mark a to-do as done; it moves to the Logbook.

    Args:
        id: uuid of the to-do.
    """
    return writes.complete_todo(id)


@mcp.tool(title="Cancel To-do", annotations=MODIFY)
@_safe
def cancel_todo(id: str) -> Any:
    """Mark a to-do as canceled — done with, but not accomplished. It moves to
    the Logbook.

    Args:
        id: uuid of the to-do.
    """
    return writes.cancel_todo(id)


# ---- Diagnostics ----
@mcp.tool(name="doctor", title="Diagnose Setup", annotations=READ_ONLY)
@_safe
def doctor_check() -> Any:
    """Check that this server can reach Things: is the database present, is it
    readable (Full Disk Access), and are Things URLs enabled for writes? Run
    this first when any other tool returns a permissions or URL error."""
    return doctor.run_checks()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
