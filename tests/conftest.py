import pathlib
import pytest

FIXTURE_DB = pathlib.Path(__file__).parent / "fixtures" / "main.sqlite"


@pytest.fixture
def fixture_db() -> str:
    assert FIXTURE_DB.is_file(), "vendored fixture DB missing"
    return str(FIXTURE_DB)
