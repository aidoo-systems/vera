from __future__ import annotations

import logging
import os
import shutil
import uuid
from typing import BinaryIO, Protocol

from fastapi import UploadFile

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
logger = logging.getLogger("vera.storage")


def ensure_data_dir() -> str:
    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


class UploadLike(Protocol):
    filename: str | None
    file: BinaryIO


def save_upload(file: UploadFile | UploadLike) -> tuple[str, str, str]:
    data_dir = ensure_data_dir()
    extension = os.path.splitext(file.filename or "")[-1].lower()
    logger.debug("Save upload filename=%s extension=%s", file.filename, extension)
    if extension not in SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS:
        logger.warning("Unsupported file type extension=%s", extension)
        raise ValueError("unsupported_file_type")
    document_id = uuid.uuid4().hex
    filename = f"{document_id}{extension}"
    original_path = os.path.join(data_dir, filename)
    with open(original_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if extension in SUPPORTED_PDF_EXTENSIONS:
        try:
            from pdf2image import convert_from_path
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pdf_support_not_installed") from exc

        images = convert_from_path(original_path, fmt="png", first_page=1, last_page=1)
        if not images:
            raise RuntimeError("pdf_no_pages")
        logger.info("PDF converted filename=%s pages=%s", file.filename, len(images))
        image_filename = f"{document_id}.png"
        image_path = os.path.join(data_dir, image_filename)
        images[0].save(image_path, "PNG")
        image_url = f"/files/{image_filename}"
        return document_id, image_path, image_url

    image_url = f"/files/{filename}"
    return document_id, original_path, image_url
