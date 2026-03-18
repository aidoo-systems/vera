"""Tests for auth service — app/services/auth.py.

Covers Redis session storage, CSRF token management, Hub auth delegation,
and license checking.
"""

import json
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services import auth as auth_module
from app.services.auth import (
    CSRF_PREFIX,
    CSRF_TOKEN_MAX_AGE,
    SESSION_MAX_AGE,
    SESSION_PREFIX,
    _LICENSE_CACHE_TTL,
    check_license,
    create_session,
    delete_session,
    generate_csrf_token,
    get_session,
    hub_configured,
    validate_csrf_token,
    validate_with_hub,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal in-memory Redis mock with setex, get, getdel, delete."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value
        self._ttls[key] = ttl

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def getdel(self, key: str) -> str | None:
        return self._store.pop(key, None)

    def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            self._ttls.pop(key, None)
            return 1
        return 0


@pytest.fixture
def fake_redis():
    """Provide a FakeRedis instance and patch _get_redis to return it."""
    r = FakeRedis()
    with patch("app.services.auth._get_redis", return_value=r):
        yield r


@pytest.fixture(autouse=True)
def _clear_license_cache():
    """Reset the module-level license cache before and after each test."""
    auth_module._license_cache = None
    auth_module._license_cache_time = 0
    yield
    auth_module._license_cache = None
    auth_module._license_cache_time = 0


# ---------------------------------------------------------------------------
# hub_configured()
# ---------------------------------------------------------------------------


def test_hub_configured_returns_false_when_no_env(monkeypatch):
    monkeypatch.delenv("HUB_BASE_URL", raising=False)
    monkeypatch.delenv("HUB_AUTH_API_KEY", raising=False)
    assert hub_configured() is False


def test_hub_configured_returns_false_when_only_url(monkeypatch):
    monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
    monkeypatch.delenv("HUB_AUTH_API_KEY", raising=False)
    with patch("app.services.auth._read_secret", return_value=""):
        assert hub_configured() is False


def test_hub_configured_returns_true_when_both_set(monkeypatch):
    monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
    monkeypatch.setenv("HUB_AUTH_API_KEY", "secret-key")
    assert hub_configured() is True


# ---------------------------------------------------------------------------
# Redis session storage
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_returns_session_id(self, fake_redis):
        session_id = create_session({"username": "alice", "role": "admin"})
        assert isinstance(session_id, str)
        assert len(session_id) > 10

    def test_stores_user_data_in_redis(self, fake_redis):
        session_id = create_session({"username": "bob", "role": "user"})
        key = f"{SESSION_PREFIX}{session_id}"
        raw = fake_redis.get(key)
        assert raw is not None
        data = json.loads(raw)
        assert data["username"] == "bob"
        assert data["role"] == "user"
        assert "created_at" in data

    def test_sets_ttl(self, fake_redis):
        session_id = create_session({"username": "carol"})
        key = f"{SESSION_PREFIX}{session_id}"
        assert fake_redis._ttls[key] == SESSION_MAX_AGE


class TestGetSession:
    def test_retrieves_existing_session(self, fake_redis):
        session_id = create_session({"username": "dave", "role": "viewer"})
        result = get_session(session_id)
        assert result is not None
        assert result["username"] == "dave"

    def test_returns_none_for_missing_session(self, fake_redis):
        result = get_session("nonexistent-id")
        assert result is None

    def test_returns_none_for_empty_id(self, fake_redis):
        result = get_session("")
        assert result is None


class TestDeleteSession:
    def test_removes_session_from_redis(self, fake_redis):
        session_id = create_session({"username": "eve"})
        assert get_session(session_id) is not None

        delete_session(session_id)
        assert get_session(session_id) is None

    def test_delete_nonexistent_session_is_safe(self, fake_redis):
        # Should not raise
        delete_session("does-not-exist")


# ---------------------------------------------------------------------------
# CSRF token management
# ---------------------------------------------------------------------------


class TestGenerateCsrfToken:
    def test_returns_token_string(self, fake_redis):
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 10

    def test_stores_token_in_redis(self, fake_redis):
        token = generate_csrf_token(session_id="sess-123")
        key = f"{CSRF_PREFIX}{token}"
        raw = fake_redis.get(key)
        assert raw is not None
        data = json.loads(raw)
        assert data["session_id"] == "sess-123"
        assert "created_at" in data

    def test_sets_ttl(self, fake_redis):
        token = generate_csrf_token()
        key = f"{CSRF_PREFIX}{token}"
        assert fake_redis._ttls[key] == CSRF_TOKEN_MAX_AGE


class TestValidateCsrfToken:
    def test_valid_token_returns_true(self, fake_redis):
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True

    def test_token_is_consumed_after_validation(self, fake_redis):
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True
        # Second use should fail (token consumed)
        assert validate_csrf_token(token) is False

    def test_invalid_token_returns_false(self, fake_redis):
        assert validate_csrf_token("nonexistent-token") is False

    def test_none_token_returns_false(self, fake_redis):
        assert validate_csrf_token(None) is False

    def test_empty_string_token_returns_false(self, fake_redis):
        assert validate_csrf_token("") is False


# ---------------------------------------------------------------------------
# validate_with_hub()
# ---------------------------------------------------------------------------


class TestValidateWithHub:
    def test_success_returns_user_dict(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        user_data = {"id": "u1", "username": "alice", "role": "admin"}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = user_data

        with patch("app.services.auth.httpx.post", return_value=mock_resp) as mock_post:
            result = validate_with_hub("alice", "password123")

        assert result == user_data
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"] == {"username": "alice", "password": "password123"}
        assert "Bearer test-key" in call_kwargs[1]["headers"]["Authorization"]

    def test_invalid_credentials_returns_none(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("app.services.auth.httpx.post", return_value=mock_resp):
            result = validate_with_hub("alice", "wrong-password")

        assert result is None

    def test_unexpected_status_returns_none(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("app.services.auth.httpx.post", return_value=mock_resp):
            result = validate_with_hub("alice", "password")

        assert result is None

    def test_hub_not_configured_returns_none(self, monkeypatch):
        monkeypatch.delenv("HUB_BASE_URL", raising=False)
        monkeypatch.delenv("HUB_AUTH_API_KEY", raising=False)
        with patch("app.services.auth._read_secret", return_value=""):
            result = validate_with_hub("alice", "password")
        assert result is None

    def test_network_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        with patch("app.services.auth.httpx.post", side_effect=httpx.ConnectError("connection refused")):
            result = validate_with_hub("alice", "password")

        assert result is None

    def test_timeout_returns_none(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        with patch("app.services.auth.httpx.post", side_effect=httpx.TimeoutException("timed out")):
            result = validate_with_hub("alice", "password")

        assert result is None


# ---------------------------------------------------------------------------
# check_license()
# ---------------------------------------------------------------------------


class TestCheckLicense:
    def test_returns_valid_license_from_hub(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        license_data = {"valid": True, "customer": "Acme Corp", "products": ["vera"], "seats": 10}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = license_data

        with patch("app.services.auth.httpx.get", return_value=mock_resp):
            result = check_license()

        assert result["valid"] is True
        assert result["customer"] == "Acme Corp"

    def test_hub_not_configured_returns_invalid(self, monkeypatch):
        monkeypatch.delenv("HUB_BASE_URL", raising=False)
        monkeypatch.delenv("HUB_AUTH_API_KEY", raising=False)
        with patch("app.services.auth._read_secret", return_value=""):
            result = check_license()

        assert result["valid"] is False
        assert "not configured" in result["error"]

    def test_uses_cache_within_ttl(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        license_data = {"valid": True, "customer": "Cached Corp", "products": ["vera"], "seats": 5}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = license_data

        with patch("app.services.auth.httpx.get", return_value=mock_resp) as mock_get:
            first = check_license()
            second = check_license()

        # Only one HTTP call — second used cache
        mock_get.assert_called_once()
        assert first == second

    def test_cache_expires_after_ttl(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        license_data = {"valid": True, "products": ["vera"], "seats": 5}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = license_data

        with patch("app.services.auth.httpx.get", return_value=mock_resp):
            check_license()

        # Expire the cache
        auth_module._license_cache_time = time.time() - _LICENSE_CACHE_TTL - 1

        with patch("app.services.auth.httpx.get", return_value=mock_resp) as mock_get:
            check_license()

        mock_get.assert_called_once()

    def test_network_error_returns_cached_if_available(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        # Populate cache
        cached = {"valid": True, "customer": "Cached", "products": ["vera"], "seats": 5}
        auth_module._license_cache = cached
        auth_module._license_cache_time = time.time() - _LICENSE_CACHE_TTL - 1  # expired

        with patch("app.services.auth.httpx.get", side_effect=httpx.ConnectError("down")):
            result = check_license()

        # Falls back to stale cache
        assert result["valid"] is True
        assert result["customer"] == "Cached"

    def test_network_error_no_cache_returns_invalid(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        with patch("app.services.auth.httpx.get", side_effect=httpx.ConnectError("down")):
            result = check_license()

        assert result["valid"] is False
        assert "failed" in result["error"].lower()

    def test_non_200_response_returns_invalid(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("app.services.auth.httpx.get", return_value=mock_resp):
            result = check_license()

        assert result["valid"] is False

    def test_sends_bearer_token(self, monkeypatch):
        monkeypatch.setenv("HUB_BASE_URL", "http://hub:2000")
        monkeypatch.setenv("HUB_AUTH_API_KEY", "my-api-key")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"valid": True, "products": [], "seats": 0}

        with patch("app.services.auth.httpx.get", return_value=mock_resp) as mock_get:
            check_license()

        call_args = mock_get.call_args
        assert call_args[1]["headers"]["Authorization"] == "Bearer my-api-key"
        assert "/api/license/status" in call_args[0][0]


# ---------------------------------------------------------------------------
# _read_secret()
# ---------------------------------------------------------------------------


class TestReadSecret:
    def test_reads_from_file(self, tmp_path, monkeypatch):
        from app.services.auth import _read_secret

        secret_file = tmp_path / "my_secret"
        secret_file.write_text("  file-secret-value  \n")

        with patch("app.services.auth.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.is_file.return_value = True
            mock_path_instance.read_text.return_value = "  file-secret-value  \n"

            result = _read_secret("my_secret", "FALLBACK_VAR")

        assert result == "file-secret-value"

    def test_falls_back_to_env_var(self, monkeypatch):
        from app.services.auth import _read_secret

        monkeypatch.setenv("MY_FALLBACK", "env-value")

        with patch("app.services.auth.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.is_file.return_value = False

            result = _read_secret("missing_secret", "MY_FALLBACK")

        assert result == "env-value"

    def test_returns_empty_when_no_file_or_env(self, monkeypatch):
        from app.services.auth import _read_secret

        monkeypatch.delenv("MISSING_VAR", raising=False)

        with patch("app.services.auth.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.is_file.return_value = False

            result = _read_secret("missing_secret", "MISSING_VAR")

        assert result == ""
