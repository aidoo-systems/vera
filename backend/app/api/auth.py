"""Auth route handlers: login, logout, CSRF, auth status."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.auth import (
    HubUnavailableError,
    create_session,
    delete_session,
    generate_csrf_token,
    get_session as get_auth_session,
    hub_configured,
    validate_with_hub,
)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, body: LoginRequest):
    """Authenticate via Hub and create a session."""
    from fastapi import HTTPException

    if not hub_configured():
        raise HTTPException(status_code=503, detail="Authentication not configured")

    try:
        user = validate_with_hub(body.username, body.password)
    except HubUnavailableError:
        raise HTTPException(status_code=503, detail="Authentication service unavailable. Please try again later.")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = create_session({
        "username": user["username"],
        "role": user.get("role", "user"),
        "user_id": user.get("id"),
    })

    response = JSONResponse({"username": user["username"], "role": user.get("role", "user")})
    secure_cookie = os.getenv("SECURE_COOKIES", "true").lower() == "true"
    response.set_cookie(
        key="vera_session",
        value=session_id,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=86400,
    )
    return response


@router.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Clear the session."""
    session_id = request.cookies.get("vera_session")
    if session_id:
        delete_session(session_id)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("vera_session")
    return response


@router.get("/api/auth/status")
async def auth_status(request: Request):
    """Check current auth status."""
    if not hub_configured():
        return JSONResponse({"authenticated": True, "auth_required": False})

    session_id = request.cookies.get("vera_session")
    if not session_id:
        return JSONResponse({"authenticated": False, "auth_required": True})

    session = get_auth_session(session_id)
    if not session:
        return JSONResponse({"authenticated": False, "auth_required": True})

    return JSONResponse({
        "authenticated": True,
        "auth_required": True,
        "username": session.get("username"),
        "role": session.get("role"),
    })


@router.get("/api/csrf-token")
async def get_csrf_token(request: Request):
    """Issue a CSRF token for the current session."""
    session_id = request.cookies.get("vera_session", "")
    token = generate_csrf_token(session_id)
    return JSONResponse({"csrf_token": token})
