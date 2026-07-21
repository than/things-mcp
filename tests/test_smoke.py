def test_package_imports():
    import things_mcp

    assert things_mcp.__version__ == "0.1.0"


def test_deps_import():
    import mcp  # noqa: F401
    import things  # noqa: F401
