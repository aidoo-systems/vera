"""VERA API route modules."""

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.export import router as export_router
from app.api.license import router as license_router
from app.api.llm import router as llm_router

__all__ = [
    "auth_router",
    "documents_router",
    "export_router",
    "license_router",
    "llm_router",
]
