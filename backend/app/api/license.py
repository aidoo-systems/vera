"""License status and cache management routes."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.middleware.auth import require_auth
from app.services.auth import check_license, refresh_license_cache

logger = logging.getLogger("vera")
router = APIRouter()


@router.get("/api/license/status")
async def license_status_proxy(_auth=Depends(require_auth)):
    """Proxy license status from Hub for the frontend."""
    status = check_license()
    return JSONResponse(status)


@router.post("/internal/license/refresh")
async def license_refresh(request: Request):
    """Force-refresh the license cache by querying Hub now.

    Internal endpoint — not exposed to end users. Call from Hub or ops
    tooling to propagate a revocation or key change without waiting for
    the hourly Beat task.
    """
    refresh_license_cache()
    status = check_license()
    logger.info("License cache manually refreshed: enforcement=%s", status.get("enforcement_level"))
    return JSONResponse({"status": "refreshed", **status})
