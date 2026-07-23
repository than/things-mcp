# things-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server for [Things 3](https://culturedcode.com/things/) on macOS. It lets Claude (Claude Code **and** Claude Desktop) read and write your tasks.

**How it works — the reliable combination:**

| Operation | Mechanism | Why |
|-----------|-----------|-----|
| **Reads** (todos, projects, areas, tags, search) | Read-only SQLite via [`things.py`](https://github.com/thingsapi/things.py) | Fast, complete, works on large libraries. Read-only **cannot corrupt** the database. |
| **Writes** (create / update / complete) | Official `things:///` URL scheme | Cultured Code's sanctioned write path. Never touches the DB directly. |

This split is deliberate: Things' own guidance warns that *writing* to its database can cause data loss, so this server **never** does. Reads open the DB read-only; every mutation goes through the URL scheme.

## Read backends: SQLite vs AppleScript

Reads have two backends. By default the server **auto-selects**: SQLite if it can reach the database (Full Disk Access granted), otherwise AppleScript.

| | **SQLite** (default when FDA granted) | **AppleScript** (fallback) |
|---|---|---|
| Full Disk Access | **Required** | Not needed (uses Automation permission, auto-prompted) |
| Things must be running | No | Yes |
| Speed | Instant | Fast for most views; a few seconds for large all-todo lists |
| Field coverage | Complete | Core fields (no checklist items, no per-item project/area) |

**Why this matters for Claude Desktop:** granting Full Disk Access to `Claude.app` does not always propagate to the process it spawns, so SQLite can stay blocked. The AppleScript backend sidesteps that entirely — set `THINGS_MCP_BACKEND=applescript` (below) and you only need the one-click Automation prompt.

### Configuration (env vars)

- `THINGS_MCP_BACKEND` — `auto` (default) · `sqlite` · `applescript`.
- `THINGS_AUTH_TOKEN` — the Things URL token for updates/complete/cancel. Only needed on the AppleScript backend (where the token can't be read from the DB). Copy it from **Things → Settings → General → Enable Things URLs → Manage**.
- `THINGSDB` — override the database path (rarely needed; it's auto-discovered).

## Requirements

- **macOS** (Things is Mac/iOS only; this server must run on the same Mac as Things).
- **Things 3**, opened at least once so its database exists.
- **Python ≥ 3.11** and [`uv`](https://docs.astral.sh/uv/).

## Setup — do this first (it's the #1 reason task servers "don't work")

### 1. Grant Full Disk Access (required for reads)

The Things database lives in a macOS-protected container. Without **Full Disk Access**, macOS blocks all reads with `Operation not permitted` — and naive servers silently report "no tasks found" instead of explaining why.

Grant it to **the app that launches this server**:

- **Claude Code** → your terminal app (Terminal, iTerm2, etc.).
- **Claude Desktop** → `Claude.app`.

**System Settings → Privacy & Security → Full Disk Access →** enable that app, then **fully quit and reopen it**.

### 2. Enable Things URLs (required for writes)

**Things → Settings → General → Enable Things URLs.** This lets the server create and update items, and provides the auth token (read automatically — you never paste it).

## Install

No clone required — [`uv`](https://docs.astral.sh/uv/) builds and runs it straight from GitHub.

### Claude Code

```bash
claude mcp add -s user things -- uvx --from git+https://github.com/than/things-mcp things-mcp
```

(`-s user` makes it available in every project. Drop it to scope the server to the current project only.)

### Claude Desktop

Recommended: the **AppleScript backend** — no Full Disk Access needed, just one Automation click. (On Desktop, Full Disk Access granted to `Claude.app` often does not reach the process it spawns, so SQLite can stay blocked.)

1. **Copy your token:** Things → Settings → General → Enable Things URLs → **Manage** → copy the token.
2. **Edit** `~/Library/Application Support/Claude/claude_desktop_config.json` and add the `things` server (paste your token):

   ```json
   {
     "mcpServers": {
       "things": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/than/things-mcp", "things-mcp"],
         "env": {
           "THINGS_MCP_BACKEND": "applescript",
           "THINGS_AUTH_TOKEN": "paste-token-here"
         }
       }
     }
   }
   ```

3. **Quit Claude Desktop (⌘Q) and reopen.**
4. Ask it "show my Things today" → click **Allow** on the *"uvx wants to control Things"* prompt.

Prefer fast SQLite instead? Drop the `env` block, grant **Full Disk Access** to `Claude.app` (and, if reads still fail, to the `uvx`/interpreter binary), then relaunch.

### Local checkout (development)

If you've cloned the repo and want to run your working copy:

```bash
claude mcp add -s user things -- uv run --directory /ABSOLUTE/PATH/things-mcp things-mcp
```

## Verify

Ask Claude to **run the `doctor` tool**. All three checks should pass:

- `database_found` — the Things DB was located.
- `database_readable` — Full Disk Access is granted (no TCC block).
- `things_urls_enabled` — the auth token is available.

Any failure comes with the exact fix.

## Tools

### Reads
| Tool | Description |
|------|-------------|
| `list_inbox` | To-dos in the Inbox |
| `list_today` | To-dos scheduled for Today (plus overdue) |
| `list_upcoming` | Scheduled future to-dos |
| `list_anytime` | To-dos in Anytime |
| `list_someday` | To-dos in Someday |
| `list_logbook` | Completed / canceled to-dos |
| `list_todos` | To-dos filtered by project / area / tag / status / deadline |
| `list_projects` | Projects (optionally by area) |
| `list_areas` | All areas |
| `list_tags` | All tag titles |
| `search` | Search to-dos/projects by title and notes |
| `get_item` | Fetch one item by uuid (with checklist items) |
| `list_recent` | Items created within an offset like `3d`, `1w`, `1y` |

### Writes
| Tool | Description |
|------|-------------|
| `add_todo` | Create a to-do (title, notes, when, deadline, tags, checklist, list, heading) |
| `add_project` | Create a project, optionally pre-filled with to-dos |
| `update_todo` | Update a to-do by id |
| `update_project` | Update a project by id |
| `complete_todo` | Mark a to-do complete |
| `cancel_todo` | Mark a to-do canceled |

### Diagnostics
| Tool | Description |
|------|-------------|
| `doctor` | Preflight: DB found? readable (Full Disk Access)? Things URLs enabled? |

## Known limitations (v1)

- **Creating areas or tags isn't supported** — the URL scheme can't create them (only AppleScript can). Areas and tags are read-only; you can *apply* existing tags when adding/updating.
- **Write confirmation is best-effort.** The URL scheme doesn't return the new item's ID, so after an `add` the server reads the list back and tries to match by title. If it can't confirm, it says so rather than inventing an ID.
- **macOS only**, by nature.

## Development

```bash
uv sync
uv run pytest          # full suite runs against a vendored fixture DB — no live Things needed
```

Read tests run against a Things-schema fixture database vendored from `things.py` (see `tests/fixtures/README.md`).

## Credits

- Reading is powered by [`things.py`](https://github.com/thingsapi/things.py) (MIT).
- Built against Cultured Code's official docs:
  [URL scheme](https://culturedcode.com/things/support/articles/2803573/),
  [JSON command](https://culturedcode.com/things/support/articles/4562654/),
  [AppleScript](https://culturedcode.com/things/support/articles/2803572/),
  [AI tools & safe integration](https://culturedcode.com/things/support/articles/5510170/).

## License

MIT — see [LICENSE](LICENSE).
