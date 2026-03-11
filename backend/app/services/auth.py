"""Authentication service — validates credentials against Hub."""

import logging
import os
import secrets
import time
from pathlib import Path
from threading import Lock

import httpx

logger = logging.getLogger(__name__)

# In-memory session storage
_sessions: dict[str, dict] = {}
_sessions_lock = Lock()
SESSION_MAX_AGE = 86400  # 24 hours

# CSRF token storage
_csrf_tokens: dict[str, tuple[str, float]] = {}
_csrf_lock = Lock()
CSRF_TOKEN_MAX_AGE = 3600  # 1 hour


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
    """Create a new session. Returns session ID."""
    session_id = secrets.token_urlsafe(32)
    with _sessions_lock:
        _cleanup_expired()
        _sessions[session_id] = {
            **user_data,
            "created_at": time.time(),
        }
    return session_id


def get_session(session_id: str) -> dict | None:
    """Get session data. Returns None if expired or missing."""
    with _sessions_lock:
        session = _sessions.get(session_id)
        if session:
            if time.time() - session.get("created_at", 0) > SESSION_MAX_AGE:
                del _sessions[session_id]
                return None
        return session


def delete_session(session_id: str) -> None:
    """Delete a session."""
    with _sessions_lock:
        _sessions.pop(session_id, None)


def _cleanup_expired() -> None:
    """Remove expired sessions (must be called under lock)."""
    now = time.time()
    expired = [sid for sid, data in _sessions.items() if now - data.get("created_at", 0) > SESSION_MAX_AGE]
    for sid in expired:
        del _sessions[sid]


def generate_csrf_token(session_id: str = "") -> str:
    """Generate a CSRF token."""
    token = secrets.token_urlsafe(32)
    with _csrf_lock:
        now = time.time()
        expired = [t for t, (_, created) in _csrf_tokens.items() if now - created > CSRF_TOKEN_MAX_AGE]
        for t in expired:
            del _csrf_tokens[t]
        _csrf_tokens[token] = (session_id, now)
    return token


def validate_csrf_token(token: str | None) -> bool:
    """Validate and consume a CSRF token."""
    if not token:
        return False
    with _csrf_lock:
        data = _csrf_tokens.get(token)
        if not data:
            return False
        _, created_at = data
        if time.time() - created_at > CSRF_TOKEN_MAX_AGE:
            del _csrf_tokens[token]
            return False
        del _csrf_tokens[token]
        return True
