from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import uuid
from typing import Any

from fastapi import UploadFile
from PIL import Image

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document, Token
from app.schemas.documents import DocumentStatus, TokenConfidenceLabel, TokenSchema
from app.services.confidence import classify_confidence, detect_forced_flags
from app.services.storage import save_upload


@dataclass
class OcrResult:
    document_id: str
    image_url: str
    tokens: list[TokenSchema]
    status: DocumentStatus
    image_width: int
    image_height: int


def _bbox_hash(bbox: tuple[float, float, float, float]) -> str:
    raw = f"{bbox[0]}-{bbox[1]}-{bbox[2]}-{bbox[3]}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10]


def _line_group_tokens(raw_tokens: list[dict]) -> list[dict]:
    if not raw_tokens:
        return []

    sorted_tokens = sorted(raw_tokens, key=lambda t: (t["bbox"][1], t["bbox"][0]))
    lines: list[list[dict]] = []
    current: list[dict] = []
    current_y: float | None = None
    threshold = 12.0

    for token in sorted_tokens:
        y = token["bbox"][1]
        if current_y is None or abs(y - current_y) <= threshold:
            current.append(token)
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            lines.append(sorted(current, key=lambda t: t["bbox"][0]))
            current = [token]
            current_y = y
    if current:
        lines.append(sorted(current, key=lambda t: t["bbox"][0]))

    flattened: list[dict] = []
    for line_index, line in enumerate(lines):
        for token_index, token in enumerate(line):
            token["line_index"] = line_index
            token["token_index"] = token_index
            token["line_id"] = f"line-{line_index}"
            flattened.append(token)
    return flattened


def _extract_tokens(image_path: str) -> list[dict]:
    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        logger.exception("PaddleOCR import failed")
        raise RuntimeError("paddleocr_not_installed") from exc

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except Exception as exc:  # pragma: no cover
        logger.exception("OCR init failed")
        raise RuntimeError("ocr_init_failed") from exc

    try:
        result = ocr.ocr(image_path, cls=True)
    except Exception as exc:  # pragma: no cover
        logger.exception("OCR failed image_path=%s", image_path)
        raise RuntimeError("ocr_failed") from exc
    tokens: list[dict[str, Any]] = []

    for line in result:
        for item in line:
            bbox_points = item[0]
            text = item[1][0]
            confidence = float(item[1][1])

            xs = [point[0] for point in bbox_points]
            ys = [point[1] for point in bbox_points]
            x_min, y_min = min(xs), min(ys)
            x_max, y_max = max(xs), max(ys)
            bbox = (float(x_min), float(y_min), float(x_max - x_min), float(y_max - y_min))

            tokens.append({"text": text, "confidence": confidence, "bbox": bbox})

    logger.info("OCR extracted tokens count=%s", len(tokens))
    return tokens


def run_ocr_for_document(document_id: str, image_path: str, image_url: str) -> OcrResult:
    Base.metadata.create_all(bind=engine)
    logger.info("OCR start document_id=%s", document_id)
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    raw_tokens = _extract_tokens(image_path)
    grouped_tokens = _line_group_tokens(raw_tokens)
    token_schemas: list[TokenSchema] = []

    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError("document_not_found")

        session.execute(Token.__table__.delete().where(Token.document_id == document_id))
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(
                image_path=image_path,
                image_width=image_width,
                image_height=image_height,
                status=DocumentStatus.ocr_done.value,
            )
        )

        for raw in grouped_tokens:
            confidence_label = TokenConfidenceLabel(classify_confidence(raw["confidence"]))
            flags = detect_forced_flags(raw["text"])
            forced_review = confidence_label != TokenConfidenceLabel.trusted or len(flags) > 0
            bbox = raw["bbox"]
            token_id = (
                f"{document_id}-l{raw['line_index']}-t{raw['token_index']}-{_bbox_hash(bbox)}"
            )

            token = Token(
                id=token_id,
                document_id=document_id,
                line_index=raw["line_index"],
                token_index=raw["token_index"],
                text=raw["text"],
                confidence=raw["confidence"],
                confidence_label=confidence_label.value,
                forced_review=forced_review,
                line_id=raw["line_id"],
                bbox=json.dumps(bbox),
                flags=json.dumps(flags),
            )
            session.add(token)

            token_schemas.append(
                TokenSchema(
                    id=token_id,
                    line_id=raw["line_id"],
                    line_index=raw["line_index"],
                    token_index=raw["token_index"],
                    text=raw["text"],
                    confidence=raw["confidence"],
                    confidence_label=confidence_label,
                    forced_review=forced_review,
                    bbox=bbox,
                    flags=flags,
                )
            )

        session.commit()

    with get_session() as session:
        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                document_id=document_id,
                event_type="ocr_completed",
                detail=json.dumps({"token_count": len(token_schemas)}),
            )
        )
        session.commit()

    return OcrResult(
        document_id=document_id,
        image_url=image_url,
        tokens=token_schemas,
        status=DocumentStatus.ocr_done,
        image_width=image_width,
        image_height=image_height,
    )


async def run_ocr(file: UploadFile) -> OcrResult:
    Base.metadata.create_all(bind=engine)
    logger.info("OCR start filename=%s", file.filename)
    document_id, image_path, image_url = save_upload(file)
    with get_session() as session:
        session.add(
            Document(
                id=document_id,
                image_path=image_path,
                image_width=0,
                image_height=0,
                status=DocumentStatus.processing.value,
                structured_fields=json.dumps({}),
            )
        )
        session.commit()

    return run_ocr_for_document(document_id, image_path, image_url)
logger = logging.getLogger("vera.ocr")
