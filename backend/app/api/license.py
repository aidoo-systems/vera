"""License status route handler."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.middleware.auth import require_auth
from app.services.auth import check_license

logger = logging.getLogger("vera")
router = APIRouter()


@router.get("/api/license/status")
async def license_status_proxy(_auth=Depends(require_auth)):
    """Proxy license status from Hub for the frontend."""
    status = check_license()
    return JSONResponse(status)
