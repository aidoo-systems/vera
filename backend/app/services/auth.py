"""Authentication service — validates credentials against Hub."""

import json
import logging
import os
import secrets
import time
from pathlib import Path

import httpx
import redis

logger = logging.getLogger(__name__)

SESSION_MAX_AGE = 86400  # 24 hours
CSRF_TOKEN_MAX_AGE = 3600  # 1 hour

SESSION_PREFIX = "vera:session:"
CSRF_PREFIX = "vera:csrf:"


def _get_redis() -> redis.Redis:
    """Get a Redis connection using the Celery broker URL."""
    url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)


def _read_secret(name: str, fallback_env: str = "") -> str:
    """Read a Docker secret from /run/secrets/, falling back to an env var."""
    path = Path(f"/run/secrets/{name}")
    if path.is_file():
        return path.read_text().strip()
    return os.environ.get(fallback_env, "")


def _get_hub_base_url() -> str:
    return os.environ.get("HUB_BASE_URL", "")


def _get_hub_api_key() -> str:
    return _read_secret("hub_auth_api_key", "HUB_AUTH_API_KEY")


def hub_configured() -> bool:
    """Check if Hub integration is configured."""
    return bool(_get_hub_base_url() and _get_hub_api_key())


# License cache
_license_cache: dict | None = None
_license_cache_time: float = 0
_LICENSE_CACHE_TTL = 3600  # 1 hour

# Allowed paths that bypass enforcement even in hard lockdown
_ALWAYS_ALLOWED_PATHS = frozenset({"/health", "/metrics", "/api/auth/login", "/api/auth/logout", "/api/auth/status", "/api/csrf-token"})


def check_license() -> dict:
    """Check license status from Hub. Cached for 1 hour.

    Returns dict with 'valid', 'products', 'seats', 'customer', 'tier',
    'enforcement_level', 'days_until_expiry', 'grace_days_remaining', 'error'.
    """
    global _license_cache, _license_cache_time

    if _license_cache and (time.time() - _license_cache_time) < _LICENSE_CACHE_TTL:
        return _license_cache

    hub_url = _get_hub_base_url()
    hub_key = _get_hub_api_key()

    if not hub_url or not hub_key:
        result = {"valid": False, "error": "Hub not configured", "products": [], "seats": 0, "enforcement_level": "grace"}
        _license_cache = result
        _license_cache_time = time.time()
        return result

    try:
        resp = httpx.get(
            f"{hub_url}/api/license/status",
            headers={"Authorization": f"Bearer {hub_key}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            result = resp.json()
            # Ensure enforcement_level is present (backward compat with older Hub)
            if "enforcement_level" not in result:
                result["enforcement_level"] = "licensed" if result.get("valid") else "soft"
            _license_cache = result
            _license_cache_time = time.time()
            return result
    except httpx.HTTPError as exc:
        logger.error("License check failed: %s", exc)
        if _license_cache:
            return _license_cache

    result = {"valid": False, "error": "License check failed", "products": [], "seats": 0, "enforcement_level": "grace"}
    _license_cache = result
    _license_cache_time = time.time()
    return result


def get_enforcement_level() -> str:
    """Get cached enforcement level. Returns 'grace' if not yet checked."""
    if _license_cache:
        return _license_cache.get("enforcement_level", "grace")
    return "grace"


def is_path_enforcement_exempt(path: str) -> bool:
    """Check if a request path is exempt from license enforcement."""
    return path in _ALWAYS_ALLOWED_PATHS or path.startswith("/files/") or path.startswith("/static/")


def validate_with_hub(username: str, password: str) -> dict | None:
    """Validate credentials against Hub's /api/auth/validate endpoint.

    Returns user dict {id, username, role} on success, None on failure.
    """
    hub_url = _get_hub_base_url()
    hub_key = _get_hub_api_key()

    if not hub_url or not hub_key:
        logger.warning("Hub auth not configured")
        return None

    try:
        resp = httpx.post(
            f"{hub_url}/api/auth/validate",
            json={"username": username, "password": password},
            headers={"Authorization": f"Bearer {hub_key}"},
            timeout=10.0,
        )

        if resp.status_code == 200:
            logger.info("Hub auth success for user '%s'", username)
            return resp.json()
        elif resp.status_code == 401:
            logger.debug("Hub auth failed for user '%s'", username)
            return None
        else:
            logger.warning("Hub auth unexpected status %s", resp.status_code)
            return None

    except httpx.HTTPError as exc:
        logger.error("Hub auth request failed: %s", exc)
        return None


def create_session(user_data: dict) -> str:
    """Create a new session in Redis. Returns session ID."""
    session_id = secrets.token_urlsafe(32)
    r = _get_redis()
    data = {**user_data, "created_at": time.time()}
    r.setex(f"{SESSION_PREFIX}{session_id}", SESSION_MAX_AGE, json.dumps(data))
    return session_id


def get_session(session_id: str) -> dict | None:
    """Get session data from Redis. Returns None if expired or missing."""
    r = _get_redis()
    raw = r.get(f"{SESSION_PREFIX}{session_id}")
    if not raw:
        return None
    return json.loads(raw)


def delete_session(session_id: str) -> None:
    """Delete a session from Redis."""
    r = _get_redis()
    r.delete(f"{SESSION_PREFIX}{session_id}")


def generate_csrf_token(session_id: str = "") -> str:
    """Generate a CSRF token and store it in Redis."""
    token = secrets.token_urlsafe(32)
    r = _get_redis()
    data = json.dumps({"session_id": session_id, "created_at": time.time()})
    r.setex(f"{CSRF_PREFIX}{token}", CSRF_TOKEN_MAX_AGE, data)
    return token


def validate_csrf_token(token: str | None) -> bool:
    """Validate and consume a CSRF token from Redis."""
    if not token:
        return False
    r = _get_redis()
    key = f"{CSRF_PREFIX}{token}"
    # Atomic get-and-delete
    raw = r.getdel(key)
    return raw is not None
