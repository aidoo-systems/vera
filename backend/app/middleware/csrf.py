"""CSRF protection middleware for VERA."""

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.services.auth import validate_csrf_token

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
    "/health",
    "/metrics",
}

EXEMPT_PREFIXES = (
    "/files/",
    "/static/",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate X-CSRF-Token header on mutating requests.

    Exempt paths (login, health) are skipped. All other POST/PUT/PATCH/DELETE
    requests must include a valid CSRF token.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)

        path = request.url.path

        if path in EXEMPT_PATHS:
            return await call_next(request)

        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        token = request.headers.get("x-csrf-token")
        if not validate_csrf_token(token):
            logger.warning("CSRF validation failed for %s %s", request.method, path)
            return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})

        return await call_next(request)
