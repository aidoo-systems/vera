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


@pytest.fixture(autouse=True)
def _stub_license_enforcement():
    """Stub license enforcement to 'grace' (full access) in all tests.

    Without this, the cold-cache default of 'soft' would cause all mutating
    endpoints to return 402, breaking unrelated tests.
    """
    import app.services.auth as auth_module

    original_cache = auth_module._license_cache
    original_time = auth_module._license_cache_time

    auth_module._license_cache = {"enforcement_level": "grace", "valid": True}
    auth_module._license_cache_time = float("inf")

    yield

    auth_module._license_cache = original_cache
    auth_module._license_cache_time = original_time
