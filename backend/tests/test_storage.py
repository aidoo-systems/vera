from __future__ import annotations

import io
import sys
import types
from unittest.mock import patch
from typing import Any, cast

from fastapi import UploadFile

import pytest
from PIL import Image

from app.services.storage import UploadLike, save_upload


class DummyUpload(UploadLike):
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(content)


def test_save_upload_rejects_unknown_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    upload = cast(UploadFile, DummyUpload("notes.txt", b"hello"))
    with pytest.raises(ValueError) as error:
        save_upload(upload)
    assert str(error.value) == "unsupported_file_type"


def test_save_upload_pdf_converts_first_page(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    upload = cast(UploadFile, DummyUpload("sample.pdf", b"%PDF-1.4"))
    fake_image = Image.new("RGB", (10, 10), "white")

    fake_pdf2image = cast(Any, types.ModuleType("pdf2image"))
    fake_pdf2image.convert_from_path = lambda *args, **kwargs: [fake_image]
    with patch.dict(sys.modules, {"pdf2image": fake_pdf2image}):
        document_id, image_path, image_url = save_upload(upload)

    assert document_id
    assert image_path.endswith(".png")
    assert image_url.endswith(".png")
    assert (tmp_path / f"{document_id}.png").exists()
