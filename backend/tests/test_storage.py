from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.storage import save_upload


class DummyUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(content)


def test_save_upload_rejects_unknown_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    upload = DummyUpload("notes.txt", b"hello")
    with pytest.raises(ValueError) as error:
        save_upload(upload)
    assert str(error.value) == "unsupported_file_type"


def test_save_upload_pdf_converts_first_page(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    upload = DummyUpload("sample.pdf", b"%PDF-1.4")
    fake_image = Image.new("RGB", (10, 10), "white")

    with patch("pdf2image.convert_from_path", return_value=[fake_image]):
        document_id, image_path, image_url = save_upload(upload)

    assert document_id
    assert image_path.endswith(".png")
    assert image_url.endswith(".png")
    assert (tmp_path / f"{document_id}.png").exists()
