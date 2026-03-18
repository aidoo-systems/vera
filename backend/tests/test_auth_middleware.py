"""Tests for auth middleware — app/middleware/auth.py.

Tests the require_auth dependency that validates session cookies.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.middleware.auth import require_auth, EXEMPT_PATHS, EXEMPT_PREFIXES


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the require_auth dependency."""
    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(_auth=Depends(require_auth)):
        return PlainTextResponse("protected content")

    @test_app.get("/health")
    async def health(_auth=Depends(require_auth)):
        return PlainTextResponse("healthy")

    @test_app.get("/metrics")
    async def metrics(_auth=Depends(require_auth)):
        return PlainTextResponse("metrics")

    @test_app.get("/api/auth/login")
    async def login(_auth=Depends(require_auth)):
        return PlainTextResponse("login")

    @test_app.get("/api/auth/logout")
    async def logout(_auth=Depends(require_auth)):
        return PlainTextResponse("logout")

    @test_app.get("/api/auth/status")
    async def status(_auth=Depends(require_auth)):
        return PlainTextResponse("status")

    @test_app.get("/files/image.png")
    async def files(_auth=Depends(require_auth)):
        return PlainTextResponse("file")

    @test_app.get("/static/app.js")
    async def static(_auth=Depends(require_auth)):
        return PlainTextResponse("static")

    return test_app


@pytest.fixture
def client():
    return TestClient(_make_app())


# ---------------------------------------------------------------------------
# Protected routes require session
# ---------------------------------------------------------------------------


def test_protected_route_rejects_no_cookie(client):
    """Requests without a vera_session cookie should get 401."""
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_protected_route_rejects_expired_session(client):
    """A session cookie pointing to an expired/missing session should get 401."""
    with patch("app.middleware.auth.get_session", return_value=None):
        response = client.get("/protected", cookies={"vera_session": "expired-id"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Session expired"


def test_protected_route_allows_valid_session(client):
    """A valid session cookie should allow access."""
    session_data = {"username": "alice", "role": "admin", "created_at": 1234567890}
    with patch("app.middleware.auth.get_session", return_value=session_data):
        response = client.get("/protected", cookies={"vera_session": "valid-session-id"})
    assert response.status_code == 200
    assert response.text == "protected content"


# ---------------------------------------------------------------------------
# Exempt paths don't require session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/health", "/metrics", "/api/auth/login", "/api/auth/logout", "/api/auth/status"],
)
def test_exempt_paths_allow_unauthenticated(client, path):
    """Exempt paths should not require authentication."""
    response = client.get(path)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Exempt prefixes don't require session
# ---------------------------------------------------------------------------


def test_files_prefix_allows_unauthenticated(client):
    """Paths under /files/ should not require authentication."""
    response = client.get("/files/image.png")
    assert response.status_code == 200
    assert response.text == "file"


def test_static_prefix_allows_unauthenticated(client):
    """Paths under /static/ should not require authentication."""
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert response.text == "static"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_exempt_paths_set():
    assert "/health" in EXEMPT_PATHS
    assert "/metrics" in EXEMPT_PATHS
    assert "/api/auth/login" in EXEMPT_PATHS
    assert "/api/auth/logout" in EXEMPT_PATHS
    assert "/api/auth/status" in EXEMPT_PATHS


def test_exempt_prefixes():
    assert "/files/" in EXEMPT_PREFIXES
    assert "/static/" in EXEMPT_PREFIXES
