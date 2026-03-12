import os
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).resolve().parent / "test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)

os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["SQLITE_PATH"] = str(TEST_DATA_DIR / "vera_test.db")


@pytest.fixture(autouse=True, scope="session")
def _disable_auth():
    """Override auth dependency so tests don't require Hub sessions."""
    from app.main import app
    from app.middleware.auth import require_auth

    app.dependency_overrides[require_auth] = lambda: None
    yield
    app.dependency_overrides.pop(require_auth, None)
