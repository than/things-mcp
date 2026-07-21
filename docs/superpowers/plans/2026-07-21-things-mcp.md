# things-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reliable macOS MCP server that reads Things 3 data (read-only SQLite via `things.py`) and writes via the official `things:///` URL scheme, with first-class handling of the two failure modes that break naive servers: TCC/Full Disk Access denial and version-dependent DB paths.

**Architecture:** One Python package (`things_mcp`) on FastMCP. Reads route through `db.find_database()` → `things.py` query functions. Writes build pure `things:///` URL strings (`urlscheme.py`), execute them via a mockable `runner.run_url`, auto-fetch the auth token, and best-effort read back the created item. A `doctor` preflight surfaces setup problems with exact remediation.

**Tech Stack:** Python ≥3.11, `mcp` 1.28.1 (FastMCP), `things.py` 1.0.1, `pytest`, managed by `uv`.

## Global Constraints

- Python: `requires-python = ">=3.11"`.
- Dependencies pinned: `mcp>=1.28,<2`, `things.py>=1.0.1,<2`. Dev: `pytest>=8`.
- Package layout: `src/things_mcp/`, import name `things_mcp`. Tests in `tests/`.
- macOS-only runtime. Never write to the Things SQLite DB — reads open it read-only (via `things.py`). All mutations go through the URL scheme.
- DB path is NEVER hardcoded — always discovered (env `THINGSDB` override, else glob).
- Errors must distinguish "not found" from `PermissionError` (TCC). Every user-facing error names the exact fix.
- Console entry point: `things-mcp` → `things_mcp.server:main`.
- Use `uv run` for all Python/pytest invocation (system python is 3.9; uv manages 3.11+).
- Commit after every task with a `feat:`/`chore:`/`test:` message ending:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/things_mcp/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable package + working `uv run pytest`. `things_mcp.__version__: str`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "things-mcp"
version = "0.1.0"
description = "Things 3 MCP server: read via things.py, write via the URL scheme."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "mcp>=1.28,<2",
    "things.py>=1.0.1,<2",
]

[project.scripts]
things-mcp = "things_mcp.server:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/things_mcp"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `src/things_mcp/__init__.py`**

```python
"""things-mcp: a Things 3 MCP server for macOS."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write `tests/__init__.py`** (empty file) and `tests/test_smoke.py`

```python
def test_package_imports():
    import things_mcp

    assert things_mcp.__version__ == "0.1.0"


def test_deps_import():
    import mcp  # noqa: F401
    import things  # noqa: F401
```

- [ ] **Step 4: Sync and run tests**

Run: `uv sync && uv run pytest -q`
Expected: 2 passed. (`uv sync` resolves mcp + things.py into `.venv`.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/things_mcp/__init__.py tests/__init__.py tests/test_smoke.py uv.lock
git commit -m "chore: scaffold things-mcp package

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: DB discovery with TCC-aware errors (`db.py`)

**Files:**
- Create: `src/things_mcp/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `THINGSDB_ENV = "THINGSDB"`
  - `class ThingsError(Exception)`
  - `class ThingsDBNotFoundError(ThingsError)`
  - `class ThingsDBPermissionError(ThingsError)`
  - `find_database() -> pathlib.Path` — returns a readable Things DB path or raises one of the above.
  - `GROUP_CONTAINER: pathlib.Path` — the TCC-protected base dir.

- [ ] **Step 1: Write failing tests `tests/test_db.py`**

```python
import os
import sqlite3
import pathlib
import pytest

from things_mcp import db


def _make_sqlite(path: pathlib.Path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x)")
    con.close()


def test_env_override_used(tmp_path, monkeypatch):
    dbfile = tmp_path / "main.sqlite"
    _make_sqlite(dbfile)
    monkeypatch.setenv(db.THINGSDB_ENV, str(dbfile))
    assert db.find_database() == dbfile


def test_env_override_missing_file_raises_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv(db.THINGSDB_ENV, str(tmp_path / "nope.sqlite"))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()


def test_permission_error_is_distinct(tmp_path, monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)

    def boom(*a, **k):
        raise PermissionError(1, "Operation not permitted")

    # Simulate TCC denial while scanning the container.
    monkeypatch.setattr(db, "_iter_candidate_dbs", boom)
    with pytest.raises(db.ThingsDBPermissionError):
        db.find_database()


def test_not_found_when_glob_empty(monkeypatch):
    monkeypatch.delenv(db.THINGSDB_ENV, raising=False)
    monkeypatch.setattr(db, "_iter_candidate_dbs", lambda: iter(()))
    with pytest.raises(db.ThingsDBNotFoundError):
        db.find_database()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL (module/attributes not defined).

- [ ] **Step 3: Implement `src/things_mcp/db.py`**

```python
"""Locate the Things 3 SQLite database with TCC-aware error reporting."""

from __future__ import annotations

import os
import pathlib
from typing import Iterator

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


def _iter_candidate_dbs() -> Iterator[pathlib.Path]:
    """Yield main.sqlite candidates under the group container.

    Raised PermissionError propagates to the caller (TCC denial).
    """
    yield from GROUP_CONTAINER.glob("**/main.sqlite")


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

    try:
        candidates = sorted(_iter_candidate_dbs(), key=lambda p: len(p.parts))
    except PermissionError as exc:
        raise ThingsDBPermissionError(_FDA_HINT) from exc

    for path in candidates:
        try:
            if _readable(path):
                return path
        except PermissionError as exc:
            raise ThingsDBPermissionError(_FDA_HINT) from exc

    raise ThingsDBNotFoundError(_NOT_FOUND_HINT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/things_mcp/db.py tests/test_db.py
git commit -m "feat: TCC-aware Things DB discovery

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Read adapter over things.py, tested against a vendored fixture DB (`reads.py`)

**Files:**
- Create: `tests/fixtures/main.sqlite` (vendored from things.py, MIT)
- Create: `tests/fixtures/README.md` (attribution)
- Create: `src/things_mcp/reads.py`
- Create: `tests/conftest.py`
- Create: `tests/test_reads.py`

**Interfaces:**
- Consumes: `db.find_database`.
- Produces (all return `list[dict]` unless noted; each accepts optional `filepath: str | None = None` used by tests):
  - `list_inbox()`, `list_today()`, `list_upcoming()`, `list_anytime()`, `list_someday()`, `list_logbook()`
  - `list_todos(project=None, area=None, tag=None, status=None, deadline=None)`
  - `list_projects(area=None)`, `list_areas()`, `list_tags() -> list[str]`
  - `search(query: str)`
  - `get_item(uuid: str) -> dict | None`
  - `list_recent(offset: str)`

- [ ] **Step 1: Vendor the fixture DB and write attribution**

Run:
```bash
mkdir -p tests/fixtures
curl -sSL -o tests/fixtures/main.sqlite \
  https://raw.githubusercontent.com/thingsapi/things.py/main/tests/main.sqlite
uv run python -c "import sqlite3,glob; con=sqlite3.connect('tests/fixtures/main.sqlite'); print(sorted(r[0] for r in con.execute(\"select name from sqlite_master where type='table'\")))"
```
Expected: prints Things tables (e.g. `TMTask`, `TMArea`, `TMTag`, `TMChecklistItem`, ...). Confirms a valid fixture.

Create `tests/fixtures/README.md`:
```markdown
# Test fixture

`main.sqlite` is vendored from the [things.py](https://github.com/thingsapi/things.py)
project's test suite (`tests/main.sqlite`), MIT licensed. It provides a real Things 3
database schema with sample data so read-adapter tests run without a live Things install.
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
import pathlib
import pytest

FIXTURE_DB = pathlib.Path(__file__).parent / "fixtures" / "main.sqlite"


@pytest.fixture
def fixture_db() -> str:
    assert FIXTURE_DB.is_file(), "vendored fixture DB missing"
    return str(FIXTURE_DB)
```

- [ ] **Step 3: Write failing tests `tests/test_reads.py`**

```python
from things_mcp import reads


def test_areas_return_dicts_with_titles(fixture_db):
    areas = reads.list_areas(filepath=fixture_db)
    assert isinstance(areas, list)
    assert all("title" in a and "uuid" in a for a in areas)


def test_tags_returns_list_of_strings(fixture_db):
    tags = reads.list_tags(filepath=fixture_db)
    assert isinstance(tags, list)
    assert all(isinstance(t, str) for t in tags)


def test_list_todos_returns_todo_items(fixture_db):
    todos = reads.list_todos(filepath=fixture_db)
    assert isinstance(todos, list)
    assert all(t.get("type") == "to-do" for t in todos)


def test_search_finds_by_title(fixture_db):
    todos = reads.list_todos(filepath=fixture_db)
    assert todos, "fixture should contain todos"
    needle = todos[0]["title"][:4]
    hits = reads.search(needle, filepath=fixture_db)
    assert any(needle in h.get("title", "") for h in hits)


def test_get_item_roundtrips_uuid(fixture_db):
    todos = reads.list_todos(filepath=fixture_db)
    uuid = todos[0]["uuid"]
    item = reads.get_item(uuid, filepath=fixture_db)
    assert item is not None and item["uuid"] == uuid


def test_projects_are_projects(fixture_db):
    projects = reads.list_projects(filepath=fixture_db)
    assert all(p.get("type") == "project" for p in projects)


def test_default_filepath_uses_find_database(monkeypatch, fixture_db):
    called = {}

    def fake_find():
        called["hit"] = True

        import pathlib

        return pathlib.Path(fixture_db)

    monkeypatch.setattr(reads.db, "find_database", fake_find)
    reads.list_areas()
    assert called.get("hit")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_reads.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 5: Implement `src/things_mcp/reads.py`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_reads.py -q`
Expected: all passed. If a `things.*` signature differs, fix the wrapper to match `things.py` 1.0.1 (the arg names above match its documented API).

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures src/things_mcp/reads.py tests/conftest.py tests/test_reads.py
git commit -m "feat: read adapter over things.py with vendored fixture DB

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Pure URL-scheme builders (`urlscheme.py`)

**Files:**
- Create: `src/things_mcp/urlscheme.py`
- Create: `tests/test_urlscheme.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `build_url(command: str, params: dict) -> str`
  - `add_todo_url(*, title=None, notes=None, when=None, deadline=None, tags=None, checklist_items=None, list=None, list_id=None, heading=None) -> str`
  - `add_project_url(*, title=None, notes=None, when=None, deadline=None, tags=None, area=None, area_id=None, todos=None) -> str`
  - `update_url(*, id, auth_token, command="update", **fields) -> str`
  - `show_url(*, id=None, query=None) -> str`
  - Encoding rules: list values for `tags` join with `,`; list values for `checklist-items`/`titles`/`to-dos` join with newline; `bool` → `"true"`/`"false"`; `None` omitted; empty string kept as `key=` (clears the field per URL scheme).

- [ ] **Step 1: Write failing tests `tests/test_urlscheme.py`**

```python
from urllib.parse import parse_qs, urlparse

from things_mcp import urlscheme as u


def test_build_url_basic_encoding():
    url = u.build_url("add", {"title": "Buy milk & eggs"})
    assert url.startswith("things:///add?")
    q = parse_qs(urlparse(url).query, keep_blank_values=True)
    assert q["title"] == ["Buy milk & eggs"]


def test_none_params_omitted():
    url = u.build_url("add", {"title": "x", "notes": None})
    assert "notes" not in urlparse(url).query


def test_bool_lowercased():
    url = u.build_url("update", {"completed": True, "canceled": False})
    q = parse_qs(urlparse(url).query)
    assert q["completed"] == ["true"]
    assert q["canceled"] == ["false"]


def test_tags_join_with_comma():
    url = u.add_todo_url(title="x", tags=["Home", "Errand"])
    q = parse_qs(urlparse(url).query)
    assert q["tags"] == ["Home,Errand"]


def test_checklist_joins_with_newline():
    url = u.add_todo_url(title="x", checklist_items=["a", "b"])
    q = parse_qs(urlparse(url).query)
    assert q["checklist-items"] == ["a\nb"]


def test_empty_string_preserved_for_clearing():
    url = u.build_url("update", {"when": ""})
    # blank value must survive so Things clears the field
    assert "when=" in urlparse(url).query


def test_update_requires_id_and_token():
    url = u.update_url(id="ABC", auth_token="tok", title="new")
    q = parse_qs(urlparse(url).query)
    assert q["id"] == ["ABC"]
    assert q["auth-token"] == ["tok"]
    assert url.startswith("things:///update?")


def test_add_project_todos_newline_joined():
    url = u.add_project_url(title="P", todos=["t1", "t2"])
    q = parse_qs(urlparse(url).query)
    assert q["to-dos"] == ["t1\nt2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_urlscheme.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/things_mcp/urlscheme.py`**

```python
"""Pure builders for things:/// URLs. No I/O, no side effects."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

_COMMA_KEYS = {"tags", "add-tags", "filter"}
_NEWLINE_KEYS = {"checklist-items", "titles", "to-dos"}


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_urlscheme.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/things_mcp/urlscheme.py tests/test_urlscheme.py
git commit -m "feat: pure things:/// URL builders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: URL runner seam (`runner.py`)

**Files:**
- Create: `src/things_mcp/runner.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class RunnerError(Exception)`
  - `run_url(url: str) -> None` — executes `open <url>`; raises `RunnerError` on non-zero exit or missing `open`.

- [ ] **Step 1: Write failing tests `tests/test_runner.py`**

```python
import subprocess
import pytest

from things_mcp import runner


def test_run_url_invokes_open(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class R:
            returncode = 0
            stderr = b""

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.run_url("things:///add?title=x")
    assert seen["cmd"][0] == "open"
    assert seen["cmd"][-1] == "things:///add?title=x"


def test_run_url_raises_on_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stderr = b"boom"

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(runner.RunnerError):
        runner.run_url("things:///add?title=x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runner.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/things_mcp/runner.py`**

```python
"""Execute a things:/// URL by shelling out to macOS `open`. Mockable seam."""

from __future__ import annotations

import subprocess


class RunnerError(Exception):
    """Executing the URL via `open` failed."""


def run_url(url: str) -> None:
    try:
        result = subprocess.run(
            ["open", "-g", url],
            capture_output=True,
        )
    except FileNotFoundError as exc:  # `open` missing → not macOS
        raise RunnerError(
            "The macOS `open` command was not found; this server runs on macOS only."
        ) from exc
    if result.returncode != 0:
        detail = getattr(result, "stderr", b"") or b""
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        raise RunnerError(f"`open` failed (exit {result.returncode}): {detail.strip()}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runner.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/things_mcp/runner.py tests/test_runner.py
git commit -m "feat: mockable open runner for URL execution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Write adapter (`writes.py`)

**Files:**
- Create: `src/things_mcp/writes.py`
- Create: `tests/test_writes.py`

**Interfaces:**
- Consumes: `urlscheme.*`, `runner.run_url`, `reads.*`, `things.token`.
- Produces (each returns `dict` with at least `{"ok": bool, "url": str}`; add returns include `"match"`):
  - `get_token() -> str` (raises `ThingsAuthError` if unavailable; caches)
  - `class ThingsAuthError(db.ThingsError)`
  - `add_todo(title, notes=None, when=None, deadline=None, tags=None, checklist_items=None, list=None, heading=None) -> dict`
  - `add_project(title, notes=None, when=None, deadline=None, tags=None, area=None, todos=None) -> dict`
  - `update_todo(id, **fields) -> dict`
  - `update_project(id, **fields) -> dict`
  - `complete_todo(id) -> dict`, `cancel_todo(id) -> dict`

- [ ] **Step 1: Write failing tests `tests/test_writes.py`**

```python
import pytest

from things_mcp import writes


@pytest.fixture(autouse=True)
def _reset_token_cache():
    writes._TOKEN_CACHE.clear()
    yield
    writes._TOKEN_CACHE.clear()


def test_add_todo_builds_and_runs(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes.reads, "list_inbox", lambda: [{"title": "Test", "uuid": "u1"}])

    result = writes.add_todo("Test")
    assert result["ok"] is True
    assert ran["url"].startswith("things:///add?")
    assert result["match"]["uuid"] == "u1"


def test_get_token_reads_things_token(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: "TKN")
    monkeypatch.setattr(writes.db, "find_database", lambda: __import__("pathlib").Path("/x"))
    assert writes.get_token() == "TKN"


def test_get_token_missing_raises(monkeypatch):
    monkeypatch.setattr(writes.things, "token", lambda **k: None)
    monkeypatch.setattr(writes.db, "find_database", lambda: __import__("pathlib").Path("/x"))
    with pytest.raises(writes.ThingsAuthError):
        writes.get_token()


def test_update_todo_includes_token(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    result = writes.update_todo("ABC", title="New")
    assert "auth-token=TKN" in ran["url"]
    assert "id=ABC" in ran["url"]
    assert result["ok"] is True


def test_complete_todo_sets_completed(monkeypatch):
    ran = {}
    monkeypatch.setattr(writes.runner, "run_url", lambda url: ran.setdefault("url", url))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    writes.complete_todo("ABC")
    assert "completed=true" in ran["url"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_writes.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/things_mcp/writes.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_writes.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/things_mcp/writes.py tests/test_writes.py
git commit -m "feat: write adapter (URL scheme + token + read-back)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Doctor preflight (`doctor.py`)

**Files:**
- Create: `src/things_mcp/doctor.py`
- Create: `tests/test_doctor.py`

**Interfaces:**
- Consumes: `db.find_database`, `writes.get_token`.
- Produces:
  - `run_checks() -> list[dict]` — each `{"name": str, "ok": bool, "detail": str, "remediation": str | None}`.
  - Checks in order: `database_found`, `database_readable`, `things_urls_enabled`.

- [ ] **Step 1: Write failing tests `tests/test_doctor.py`**

```python
import pathlib
import pytest

from things_mcp import doctor, db, writes


def test_all_pass(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    monkeypatch.setattr(writes, "get_token", lambda: "TKN")
    checks = doctor.run_checks()
    assert [c["ok"] for c in checks] == [True, True, True]


def test_permission_failure_reported(monkeypatch):
    def boom():
        raise db.ThingsDBPermissionError("FDA needed")

    monkeypatch.setattr(db, "find_database", boom)
    checks = doctor.run_checks()
    found = next(c for c in checks if c["name"] == "database_found")
    assert found["ok"] is False
    assert "Full Disk Access" in found["remediation"] or "FDA" in found["remediation"]


def test_token_failure_reported(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))

    def no_token():
        raise writes.ThingsAuthError("enable URLs")

    monkeypatch.setattr(writes, "get_token", no_token)
    checks = doctor.run_checks()
    urls = next(c for c in checks if c["name"] == "things_urls_enabled")
    assert urls["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_doctor.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/things_mcp/doctor.py`**

```python
"""Preflight diagnostics with exact remediation for each failure."""

from __future__ import annotations

from typing import Any

from things_mcp import db, writes


def run_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1 + 2: database found & readable (find_database validates readability).
    path = None
    try:
        path = db.find_database()
        checks.append(
            {"name": "database_found", "ok": True, "detail": str(path), "remediation": None}
        )
        checks.append(
            {"name": "database_readable", "ok": True, "detail": "read access OK", "remediation": None}
        )
    except db.ThingsDBPermissionError as exc:
        checks.append(
            {"name": "database_found", "ok": False, "detail": "permission denied", "remediation": str(exc)}
        )
        checks.append(
            {"name": "database_readable", "ok": False, "detail": "blocked by macOS TCC", "remediation": str(exc)}
        )
    except db.ThingsDBNotFoundError as exc:
        checks.append(
            {"name": "database_found", "ok": False, "detail": "not found", "remediation": str(exc)}
        )
        checks.append(
            {"name": "database_readable", "ok": False, "detail": "no database to read", "remediation": str(exc)}
        )

    # 3: Things URLs enabled (token present).
    if path is None:
        checks.append(
            {
                "name": "things_urls_enabled",
                "ok": False,
                "detail": "skipped (no database)",
                "remediation": "Resolve the database check first.",
            }
        )
        return checks
    try:
        writes.get_token()
        checks.append(
            {"name": "things_urls_enabled", "ok": True, "detail": "auth token present", "remediation": None}
        )
    except writes.ThingsAuthError as exc:
        checks.append(
            {"name": "things_urls_enabled", "ok": False, "detail": "no auth token", "remediation": str(exc)}
        )
    return checks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_doctor.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/things_mcp/doctor.py tests/test_doctor.py
git commit -m "feat: doctor preflight diagnostics

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: FastMCP server + entry point (`server.py`)

**Files:**
- Create: `src/things_mcp/server.py`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `reads.*`, `writes.*`, `doctor.run_checks`.
- Produces:
  - `mcp` (a `FastMCP` instance) with all tools registered.
  - `main() -> None` — runs the stdio server.
  - Read tools return `list`/`dict` from `reads`; write tools return `writes` dicts; `doctor` returns `run_checks()`.
  - Every tool wraps calls so `ThingsError`/`RunnerError` become a returned `{"error": "..."}` (never an unhandled crash).

- [ ] **Step 1: Write failing tests `tests/test_server.py`**

```python
import pathlib

from things_mcp import server, db, writes, reads


def test_tools_registered():
    # FastMCP exposes registered tool names; assert the surface is complete.
    import asyncio

    tools = asyncio.get_event_loop().run_until_complete(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_inbox", "list_today", "list_upcoming", "list_anytime",
        "list_someday", "list_logbook", "list_todos", "list_projects",
        "list_areas", "list_tags", "search", "get_item", "list_recent",
        "add_todo", "add_project", "update_todo", "update_project",
        "complete_todo", "cancel_todo", "doctor",
    }
    assert expected <= names


def test_list_areas_tool_returns_data(monkeypatch, fixture_db):
    monkeypatch.setattr(db, "find_database", lambda: pathlib.Path(fixture_db))
    out = server.list_areas()
    assert isinstance(out, list)


def test_read_tool_errors_are_caught(monkeypatch):
    def boom():
        raise db.ThingsDBPermissionError("FDA needed")

    monkeypatch.setattr(reads, "list_inbox", boom)
    out = server.list_inbox()
    assert isinstance(out, dict) and "error" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -q`
Expected: FAIL (module not defined).

- [ ] **Step 3: Implement `src/things_mcp/server.py`**

```python
"""FastMCP server exposing Things read/write tools."""

from __future__ import annotations

import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from things_mcp import db, doctor, reads, runner, writes

mcp = FastMCP("things")


def _safe(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (db.ThingsError, runner.RunnerError) as exc:
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
@mcp.tool()
def doctor_check() -> Any:
    """Preflight: DB found? readable (Full Disk Access)? Things URLs enabled?"""
    return doctor.run_checks()


# Register doctor under the name `doctor` while keeping a valid Python identifier.
doctor_check.__name__ = "doctor"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

Note: the test asserts a tool named `doctor`. FastMCP derives the tool name from the function name, so define the function as `doctor_check` and set its registered name explicitly. If FastMCP's `@mcp.tool(name="doctor")` kwarg is supported in 1.28 (it is), prefer `@mcp.tool(name="doctor")` and drop the `__name__` reassignment. During implementation, confirm which the installed version accepts and use that; adjust the test if the accepted spelling differs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_server.py -q`
Expected: 3 passed. (If FastMCP wraps sync tools differently, adapt `_safe` to match; keep the error-catching contract.)

- [ ] **Step 5: Full suite + entry-point smoke**

Run:
```bash
uv run pytest -q
uv run things-mcp &  SVPID=$! ; sleep 1 ; kill $SVPID 2>/dev/null ; echo "entry point launched"
```
Expected: all tests pass; the console script starts (stdio server; killed after 1s).

- [ ] **Step 6: Commit**

```bash
git add src/things_mcp/server.py tests/test_server.py
git commit -m "feat: FastMCP server wiring all Things tools

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: README, license, packaging polish

**Files:**
- Create: `README.md`
- Create: `LICENSE` (MIT)
- Modify: `pyproject.toml` (add `authors`, `urls`, classifiers)

**Interfaces:**
- Consumes: everything working.
- Produces: install-ready docs.

- [ ] **Step 1: Write `LICENSE`** (standard MIT text, `Copyright (c) 2026 than`).

- [ ] **Step 2: Write `README.md`** covering, in this order:
  1. One-line description + the read=SQLite / write=URL-scheme model.
  2. **Requirements:** macOS, Things 3, Python ≥3.11, `uv`.
  3. **Setup (do this first, it's the #1 failure mode):**
     - **Full Disk Access** — System Settings → Privacy & Security → Full Disk Access → enable your terminal app (Claude Code) and/or `Claude.app` (Claude Desktop). Quit and reopen after granting.
     - **Enable Things URLs** — Things → Settings → General → Enable Things URLs.
  4. **Install (Claude Code):**
     ```bash
     claude mcp add things -- uv run --directory /ABSOLUTE/PATH/things-mcp things-mcp
     ```
  5. **Install (Claude Desktop)** — `claude_desktop_config.json` snippet:
     ```json
     {
       "mcpServers": {
         "things": {
           "command": "uv",
           "args": ["run", "--directory", "/ABSOLUTE/PATH/things-mcp", "things-mcp"]
         }
       }
     }
     ```
  6. **Verify:** ask Claude to run the `doctor` tool; all three checks should be green.
  7. **Tools table** — the full read + write + doctor list with one-line descriptions.
  8. **Known limitations (v1):** no area/tag creation; write confirmation is best-effort read-back; macOS only.
  9. **Credits:** built on [`things.py`](https://github.com/thingsapi/things.py); links to the four Cultured Code articles.

- [ ] **Step 3: Add metadata to `pyproject.toml`**

```toml
authors = [{ name = "than" }]

[project.urls]
Homepage = "https://github.com/than/things-mcp"
Issues = "https://github.com/than/things-mcp/issues"
```

- [ ] **Step 4: Verify docs build/links + full suite**

Run: `uv run pytest -q && echo OK`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md LICENSE pyproject.toml
git commit -m "docs: README with FDA/URL setup, install, tools

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Create and push GitHub repo `than/things-mcp`

**Files:** none (git/remote only).

- [ ] **Step 1: Confirm `gh` auth**

Run: `gh auth status`
Expected: logged in. If not, stop and ask the user to run `! gh auth login`.

- [ ] **Step 2: Create the repo and push**

Run:
```bash
gh repo create than/things-mcp --public --source=. --remote=origin \
  --description "Things 3 MCP server for macOS: read via things.py, write via the URL scheme." --push
```
Expected: repo created, `main` pushed.

- [ ] **Step 3: Verify**

Run: `gh repo view than/things-mcp --web` (or `gh repo view than/things-mcp`)
Expected: repo exists with the pushed commits.

---

## Self-Review

**Spec coverage:**
- Reads via things.py → Task 3. Writes via URL scheme → Tasks 4–6. DB glob discovery (no hardcode) → Task 2. TCC/Full Disk Access distinct error → Tasks 2, 7, 9. Auth-token auto-fetch → Task 6. `doctor` → Task 7. No `add_area` → confirmed (not in Task 6/8 surface). Fire + read-back → Task 6. Fixture-DB testing → Task 3. Pure URL builder tests → Task 4. Packaging + both-client install → Task 9. Repo creation (user's original ask) → Task 10. All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step contains full code; every command has expected output. The one conditional (FastMCP tool-name spelling in Task 8) gives an explicit decision rule + fallback, not a placeholder.

**Type consistency:** `find_database() -> Path` used consistently (Tasks 2/3/6/7). `reads.*` signatures in Task 3 match calls in Tasks 6/8. `urlscheme.*` builders in Task 4 match `writes.py` calls in Task 6. `run_url` (Task 5) matches `writes`/tests usage. `writes.*` return dicts consumed by server (Task 8). `_TOKEN_CACHE` defined in Task 6 and referenced by its own tests. Consistent throughout.
