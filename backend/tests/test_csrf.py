"""Tests for CSRF middleware — app/middleware/csrf.py."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.middleware.csrf import CSRFMiddleware, EXEMPT_PATHS, EXEMPT_PREFIXES, MUTATING_METHODS


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with CSRF middleware for testing."""
    test_app = FastAPI()
    test_app.add_middleware(CSRFMiddleware)

    @test_app.get("/test")
    async def get_test():
        return PlainTextResponse("ok")

    @test_app.head("/test")
    async def head_test():
        return PlainTextResponse("ok")

    @test_app.post("/test")
    async def post_test():
        return PlainTextResponse("ok")

    @test_app.put("/test")
    async def put_test():
        return PlainTextResponse("ok")

    @test_app.patch("/test")
    async def patch_test():
        return PlainTextResponse("ok")

    @test_app.delete("/test")
    async def delete_test():
        return PlainTextResponse("ok")

    # Exempt endpoints
    @test_app.post("/api/auth/login")
    async def login():
        return PlainTextResponse("login ok")

    @test_app.post("/api/auth/logout")
    async def logout():
        return PlainTextResponse("logout ok")

    @test_app.post("/api/auth/status")
    async def status():
        return PlainTextResponse("status ok")

    @test_app.post("/health")
    async def health():
        return PlainTextResponse("health ok")

    @test_app.post("/metrics")
    async def metrics():
        return PlainTextResponse("metrics ok")

    @test_app.post("/files/some-file.png")
    async def files():
        return PlainTextResponse("file ok")

    @test_app.post("/static/app.js")
    async def static():
        return PlainTextResponse("static ok")

    return test_app


@pytest.fixture
def app():
    return _make_app()


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Safe methods are exempt (GET, HEAD)
# ---------------------------------------------------------------------------


def test_get_request_allowed_without_csrf(client):
    """GET requests should pass through without CSRF validation."""
    response = client.get("/test")
    assert response.status_code == 200
    assert response.text == "ok"


def test_head_request_allowed_without_csrf(client):
    """HEAD requests should pass through without CSRF validation."""
    response = client.head("/test")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Mutating methods require CSRF token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_mutating_request_rejected_without_csrf_token(client, method):
    """POST/PUT/PATCH/DELETE to non-exempt paths must include a CSRF token."""
    response = getattr(client, method)("/test")
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing or invalid"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_mutating_request_rejected_with_invalid_token(client, method):
    """An invalid/expired CSRF token should be rejected."""
    with patch("app.middleware.csrf.validate_csrf_token", return_value=False):
        response = getattr(client, method)("/test", headers={"x-csrf-token": "bad-token"})
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_mutating_request_allowed_with_valid_token(client, method):
    """A valid CSRF token should allow the request through."""
    with patch("app.middleware.csrf.validate_csrf_token", return_value=True):
        response = getattr(client, method)("/test", headers={"x-csrf-token": "valid-token"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Exempt paths bypass CSRF validation
# ---------------------------------------------------------------------------


def test_login_endpoint_exempt_from_csrf(client):
    """POST /api/auth/login should not require a CSRF token."""
    response = client.post("/api/auth/login")
    assert response.status_code == 200
    assert response.text == "login ok"


def test_logout_endpoint_exempt_from_csrf(client):
    """POST /api/auth/logout should not require a CSRF token."""
    response = client.post("/api/auth/logout")
    assert response.status_code == 200


def test_auth_status_endpoint_exempt_from_csrf(client):
    """POST /api/auth/status should not require a CSRF token."""
    response = client.post("/api/auth/status")
    assert response.status_code == 200


def test_health_endpoint_exempt_from_csrf(client):
    """POST /health should not require a CSRF token."""
    response = client.post("/health")
    assert response.status_code == 200
    assert response.text == "health ok"


def test_metrics_endpoint_exempt_from_csrf(client):
    """POST /metrics should not require a CSRF token."""
    response = client.post("/metrics")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Exempt prefixes bypass CSRF validation
# ---------------------------------------------------------------------------


def test_files_prefix_exempt_from_csrf(client):
    """Paths starting with /files/ should bypass CSRF."""
    response = client.post("/files/some-file.png")
    assert response.status_code == 200
    assert response.text == "file ok"


def test_static_prefix_exempt_from_csrf(client):
    """Paths starting with /static/ should bypass CSRF."""
    response = client.post("/static/app.js")
    assert response.status_code == 200
    assert response.text == "static ok"


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


def test_mutating_methods_set():
    """Verify the set of methods that trigger CSRF validation."""
    assert MUTATING_METHODS == {"POST", "PUT", "PATCH", "DELETE"}


def test_exempt_paths_include_expected():
    """All expected exempt paths are present."""
    assert "/api/auth/login" in EXEMPT_PATHS
    assert "/api/auth/logout" in EXEMPT_PATHS
    assert "/api/auth/status" in EXEMPT_PATHS
    assert "/health" in EXEMPT_PATHS
    assert "/metrics" in EXEMPT_PATHS


def test_exempt_prefixes_include_expected():
    """Exempt prefix tuples are correct."""
    assert "/files/" in EXEMPT_PREFIXES
    assert "/static/" in EXEMPT_PREFIXES


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_csrf_token_header_rejected(client):
    """An empty X-CSRF-Token header should be rejected."""
    with patch("app.middleware.csrf.validate_csrf_token", return_value=False):
        response = client.post("/test", headers={"x-csrf-token": ""})
    assert response.status_code == 403
