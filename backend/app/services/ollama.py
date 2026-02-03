from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _base_url() -> str:
    return os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def list_models() -> list[str]:
    url = f"{_base_url()}/api/tags"
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    models = payload.get("models", [])
    names: list[str] = []
    for model in models:
        name = model.get("name")
        if name:
            names.append(str(name))
    return sorted(names)


def pull_model(model: str) -> dict[str, Any]:
    url = f"{_base_url()}/api/pull"
    payload = {"model": model, "stream": False}
    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, json=payload)
    response.raise_for_status()
    return response.json()
