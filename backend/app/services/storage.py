from __future__ import annotations

import logging
import os
import shutil
import uuid
from typing import BinaryIO, Protocol

from fastapi import UploadFile

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}
logger = logging.getLogger("vera.storage")


def ensure_data_dir() -> str:
    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


class UploadLike(Protocol):
    filename: str | None
    file: BinaryIO


def _get_file_size(file_obj: BinaryIO) -> int | None:
    try:
        current_pos = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(current_pos)
        return size
    except Exception:  # pragma: no cover
        return None


def _validate_mime(file_obj: BinaryIO) -> None:
    try:
        import filetype
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("mime_support_not_installed") from exc

    current_pos = file_obj.tell()
    file_obj.seek(0)
    header = file_obj.read(261)
    file_obj.seek(current_pos)

    kind = filetype.guess(header)
    if kind is None or kind.mime not in SUPPORTED_MIME_TYPES:
        raise ValueError("unsupported_mime_type")


def _run_virus_scan(path: str) -> None:
    import subprocess

    command = os.getenv("VIRUS_SCAN_COMMAND")
    if not command:
        return
    result = subprocess.run([command, path], capture_output=True, timeout=120)
    if result.returncode != 0:
        raise ValueError("virus_detected")


def save_upload(file: UploadFile | UploadLike) -> tuple[str, str, str, list[dict]]:
    data_dir = ensure_data_dir()
    extension = os.path.splitext(file.filename or "")[-1].lower()
    logger.debug("Save upload filename=%s extension=%s", file.filename, extension)
    if extension not in SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS:
        logger.warning("Unsupported file type extension=%s", extension)
        raise ValueError("unsupported_file_type")

    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "25"))
    file_size = _get_file_size(file.file)
    if file_size is not None and file_size > max_upload_mb * 1024 * 1024:
        raise ValueError("file_too_large")

    if os.getenv("STRICT_MIME_VALIDATION", "1") == "1":
        _validate_mime(file.file)
    document_id = uuid.uuid4().hex
    filename = f"{document_id}{extension}"
    original_path = os.path.join(data_dir, filename)
    with open(original_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        _run_virus_scan(original_path)
    except ValueError:
        os.remove(original_path)
        raise

    if extension in SUPPORTED_PDF_EXTENSIONS:
        try:
            from pdf2image import convert_from_path
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pdf_support_not_installed") from exc

        images = convert_from_path(original_path, fmt="png")
        if not images:
            raise RuntimeError("pdf_no_pages")
        logger.info("PDF converted filename=%s pages=%s", file.filename, len(images))
        pages: list[dict] = []
        for index, image in enumerate(images):
            image_filename = f"{document_id}-page-{index}.png"
            image_path = os.path.join(data_dir, image_filename)
            image.save(image_path, "PNG")
            pages.append(
                {
                    "page_index": index,
                    "image_path": image_path,
                    "image_url": f"/files/{image_filename}",
                }
            )

        first_page = pages[0]
        return document_id, first_page["image_path"], first_page["image_url"], pages

    image_url = f"/files/{filename}"
    pages = [{"page_index": 0, "image_path": original_path, "image_url": image_url}]
    return document_id, original_path, image_url, pages
