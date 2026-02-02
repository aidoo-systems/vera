from __future__ import annotations

import os
import shutil
import uuid
from fastapi import UploadFile


def ensure_data_dir() -> str:
    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def save_upload(file: UploadFile) -> tuple[str, str, str]:
    data_dir = ensure_data_dir()
    extension = os.path.splitext(file.filename or "")[-1].lower()
    document_id = uuid.uuid4().hex
    filename = f"{document_id}{extension}"
    image_path = os.path.join(data_dir, filename)
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    image_url = f"/files/{filename}"
    return document_id, image_path, image_url
