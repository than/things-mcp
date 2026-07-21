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
