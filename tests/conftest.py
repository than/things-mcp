import pathlib
import pytest

from things_mcp import read_backend

FIXTURE_DB = pathlib.Path(__file__).parent / "fixtures" / "main.sqlite"


@pytest.fixture
def fixture_db() -> str:
    assert FIXTURE_DB.is_file(), "vendored fixture DB missing"
    return str(FIXTURE_DB)


@pytest.fixture(autouse=True)
def _reset_backend_cache():
    """The read-backend memoizes its choice; clear it so each test picks fresh."""
    read_backend.reset_cache()
    yield
    read_backend.reset_cache()
