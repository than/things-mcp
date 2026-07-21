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
