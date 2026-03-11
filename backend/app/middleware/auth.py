"""Authentication middleware for VERA."""

import logging

from fastapi import HTTPException, Request

from app.services.auth import get_session

logger = logging.getLogger(__name__)

# Paths that don't require authentication
EXEMPT_PATHS = {
    "/health",
    "/metrics",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
}

EXEMPT_PREFIXES = (
    "/files/",
    "/static/",
)


def require_auth(request: Request) -> None:
    """FastAPI dependency that requires authentication.

    Raises HTTPException(401) if not authenticated.
    """
    path = request.url.path

    # Skip auth for exempt paths
    if path in EXEMPT_PATHS:
        return
    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return

    session_id = request.cookies.get("vera_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
