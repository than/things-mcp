# things-mcp — Design Spec

**Date:** 2026-07-21
**Repo:** `than/things-mcp`
**Status:** Approved design, pending implementation plan

## Purpose

A reliable, Things-compatible MCP server that lets Claude (Claude Code + Claude Desktop) read and write to [Things 3](https://culturedcode.com/things/) on macOS.

The two Things MCP repos the user previously tried did not work. Root-cause analysis of common failure modes drove the core architectural choices below.

## Non-goals (v1)

- Cross-platform / mobile / web support — impossible by nature (see Constraints).
- Creating areas or tags — the URL scheme cannot; only AppleScript can. Areas/tags are read-only in v1.
- Synchronous capture of newly-created item IDs via x-callback-url — deferred (see Write confirmation).
- AppleScript-based reads or writes — deferred; not needed for v1.

## Constraints & platform reality

Everything here is **local-macOS-only**, regardless of MCP vs Skill:

- **Reads** open a local Things SQLite file.
- **Writes** shell out to `open things:///…` on the local machine.

Therefore the server can only run on the same Mac where Things is installed. It cannot function from mobile or web clients. This is inherent, not a limitation of the design.

## Architecture

A single Python MCP server built on **FastMCP**, importing the mature **`things.py`** library directly (no subprocess for reads). Two internal adapters isolate the two mechanisms:

```
┌─────────────────────────────────────────────┐
│              FastMCP server                   │
│  (tool definitions, validation, formatting)   │
└───────────────┬───────────────┬──────────────┘
                │               │
      ┌─────────▼──────┐ ┌──────▼───────────────┐
      │  Read adapter  │ │   Write adapter       │
      │  wraps things  │ │  builds things:/// URL │
      │  .py (SQLite   │ │  + executes via `open` │
      │  read-only)    │ │  + auto auth-token     │
      └────────────────┘ └───────────────────────┘
                │               │
      ┌─────────▼──────┐ ┌──────▼───────────────┐
      │ Things SQLite  │ │   Things.app          │
      │ DB (read-only) │ │   (URL handler)       │
      └────────────────┘ └───────────────────────┘
```

### Why read-only SQLite (via things.py) for reads

- Things' own guidance warns about **writing** to the DB causing corruption. Opening it **read-only cannot corrupt** anything.
- `things.py` is battle-tested and reads this exact DB read-only.
- AppleScript reads are the flakier path in practice: slow on large libraries, require Things running, and need an automation-permission grant that often silently fails — a likely reason the user's prior repos failed.

### Why URL scheme for writes

- The official, Cultured-Code-sanctioned write path. No automation permission needed (only "Enable Things URLs" in Settings).
- Supports checklists, headings, and batch JSON that AppleScript handles awkwardly.

## Component boundaries

Each unit has one purpose, a defined interface, and is independently testable.

| Unit | Responsibility | Interface | Depends on |
|------|----------------|-----------|------------|
| `db.py` | Locate the Things SQLite DB; expose a validated filepath; clear errors if missing | `find_database() -> Path` | filesystem glob |
| `reads.py` | Thin typed wrappers over `things.py` query functions; normalize output | `list_inbox()`, `list_todos(...)`, `search(q)`, `get_item(uuid)`, … | `things.py`, `db.py` |
| `urlscheme.py` | **Pure** function: build a `things:///` URL string from structured args | `build_url(command, **params) -> str` | none (pure) |
| `writes.py` | Execute a built URL via `open`; fetch auth-token; best-effort read-back | `add_todo(...)`, `update_todo(...)`, … | `urlscheme.py`, `reads.py`, `open` runner |
| `runner.py` | Thin wrapper around `open` (subprocess) — mockable seam for tests | `run_url(url: str) -> None` | subprocess |
| `server.py` | FastMCP tool definitions, arg schemas, response formatting | MCP tools | all of the above |

## DB path discovery (critical)

The DB lives in the app sandbox container; the exact subfolder/filename **changes between Things versions**, so it MUST be discovered by glob, never hardcoded:

```
~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/**/main.sqlite
```

`things.py` already implements this discovery (env var `THINGSDB` overrides). `db.py` wraps it and raises a precise error distinguishing:
- Things not installed / never launched,
- Things installed but never synced (no DB yet),
- DB found but unreadable (permissions).

## Tools exposed

### Reads (via things.py)
- `list_inbox`, `list_today`, `list_upcoming`, `list_anytime`, `list_someday`, `list_logbook`
- `list_todos` — filters: `project`, `area`, `tag`, `status` (incomplete/completed/canceled), `deadline`
- `list_projects`, `list_areas`, `list_tags`
- `search` — matches title + notes
- `get_item` — by uuid; includes notes + checklist items
- `list_recent` — items created within an offset like `3d` / `1w` / `1y`

### Writes (via URL scheme)
- `add_todo` — title, notes, when, deadline, tags, checklist_items, list, heading
- `add_project` — title, notes, when, deadline, tags, area, todos
- `update_todo` — id + any mutable field (auto auth-token)
- `update_project` — id + any mutable field (auto auth-token)
- `complete_todo`, `cancel_todo` — id

## Auth token handling

Update commands require an `auth-token`. `things.py` exposes `things.token()` which reads it locally. The write adapter fetches it automatically and caches it for the process lifetime. If URLs aren't enabled, the tool returns a clear, actionable message ("Enable Things URLs in Settings → General").

## Write confirmation (v1 decision)

`open` fires the URL but does not cleanly return the created item's ID. v1 approach:
1. Execute the write.
2. Best-effort **read-back**: for `add`, query the target list for a newly-created item matching the title; return it if found.
3. Report the outcome honestly — if the read-back can't confirm, say so rather than fabricating an ID.

Deferred: proper x-callback-url ID capture, or AppleScript `make new to do` (returns ID synchronously). Noted as future enhancement.

## Error handling

- **DB missing/unreadable:** precise, actionable error at tool-call time (and at server start).
- **Writes when URLs disabled / no token:** actionable message naming the exact Settings toggle.
- **Invalid args (bad date, unknown list):** validated before building the URL; return the specific problem.
- **`open` failure:** surface the subprocess error; never claim success on failure.

## Testing strategy

- **Read adapter:** tested against a checked-in **fixture SQLite DB** (a small, hand-built Things-shaped DB). No live Things needed — runs in CI.
- **URL builder:** pure function; assert exact `things:///` strings for representative inputs (encoding, multi-value, clearing values).
- **Write execution:** `runner.run_url` mocked; assert the URL passed and read-back behavior.
- **Server tools:** thin; smoke-tested that each tool wires to its adapter and formats output.

## Packaging & install

- `pyproject.toml`; installable via `uvx` / `pipx`.
- README includes:
  - the exact `claude mcp add` command (Claude Code),
  - the Claude Desktop `claude_desktop_config.json` snippet,
  - the "Enable Things URLs" one-time setup step.

## Open questions / risks

- **Fixture DB fidelity:** the checked-in fixture must resemble the real schema closely enough that `things.py` queries succeed. Mitigation: generate it by having `things.py` read a real DB once and replaying a minimal schema, or ship a tiny real (empty-ish) Things DB.
- **`things.py` schema drift:** if Things changes the schema, `things.py` (not us) must update. We pin a known-good version and surface upstream errors clearly.
