"""LLM/summary route handlers."""

import asyncio
import json
import logging
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.middleware.auth import require_admin, require_auth

_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
from app.services.ollama import list_models, pull_model, stream_pull_model
from app.services.summary import build_summary, build_page_summary

logger = logging.getLogger("vera")
router = APIRouter()


@router.get("/documents/{document_id}/summary")
async def get_summary(document_id: str, model: str | None = None, _auth=Depends(require_auth)):
    logger.info("Summary requested document_id=%s", document_id)
    try:
        summary = await asyncio.to_thread(build_summary, document_id, model_override=model)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "document_not_validated":
            raise HTTPException(status_code=409, detail="Document not validated")
        raise
    logger.info("Summary completed document_id=%s", document_id)
    return JSONResponse(summary)


@router.get("/documents/{document_id}/pages/{page_id}/summary")
async def get_page_summary(document_id: str, page_id: str, model: str | None = None, _auth=Depends(require_auth)):
    logger.info("Summary requested document_id=%s page_id=%s", document_id, page_id)
    try:
        summary = await asyncio.to_thread(build_page_summary, document_id, page_id, model_override=model)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "page_not_validated":
            raise HTTPException(status_code=409, detail="Review incomplete")
        raise
    logger.info("Page summary completed document_id=%s page_id=%s", document_id, page_id)
    return JSONResponse(summary)


@router.get("/llm/models")
async def get_llm_models(_auth=Depends(require_auth)):
    try:
        models = list_models()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Ollama is not available")
    return JSONResponse({"models": models})


@router.get("/llm/health")
async def get_llm_health(_auth=Depends(require_auth)):
    try:
        models = list_models()
    except httpx.HTTPError:
        return JSONResponse({"reachable": False, "models": [], "model": os.getenv("OLLAMA_MODEL", "llama3.1")})
    return JSONResponse({"reachable": True, "models": models, "model": os.getenv("OLLAMA_MODEL", "llama3.1")})


@router.post("/llm/models/pull")
async def pull_llm_model(payload: dict, _auth=Depends(require_admin)):
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")
    if not _MODEL_NAME_RE.match(model):
        raise HTTPException(status_code=400, detail="Invalid model name")
    try:
        result = pull_model(model)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Failed to pull model from Ollama")
    return JSONResponse({"status": "ok", "result": result})


@router.post("/llm/models/pull/stream")
async def pull_llm_model_stream(payload: dict, _auth=Depends(require_admin)):
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")
    if not _MODEL_NAME_RE.match(model):
        raise HTTPException(status_code=400, detail="Invalid model name")

    def event_stream():
        try:
            for event in stream_pull_model(model):
                yield json.dumps(event) + "\n"
        except httpx.HTTPError:
            yield json.dumps({"error": "Failed to pull model from Ollama"}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
