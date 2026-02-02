from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from fastapi import UploadFile
from PIL import Image

from app.db.session import Base, engine, get_session
from app.models.documents import Document, Token
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
        raise RuntimeError("paddleocr_not_installed") from exc

    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    result = ocr.ocr(image_path, cls=True)
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

    return tokens


async def run_ocr(file: UploadFile) -> OcrResult:
    Base.metadata.create_all(bind=engine)
    document_id, image_path, image_url = save_upload(file)
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    raw_tokens = _extract_tokens(image_path)
    grouped_tokens = _line_group_tokens(raw_tokens)
    token_schemas: list[TokenSchema] = []

    with get_session() as session:
        document = Document(
            id=document_id,
            image_path=image_path,
            image_width=image_width,
            image_height=image_height,
            status=DocumentStatus.ocr_done.value,
        )
        session.add(document)

        for raw in grouped_tokens:
            confidence_label = TokenConfidenceLabel(classify_confidence(raw["confidence"]))
            flags = detect_forced_flags(raw["text"])
            forced_review = confidence_label != TokenConfidenceLabel.trusted or len(flags) > 0
            bbox = raw["bbox"]
            token_id = f"l{raw['line_index']}-t{raw['token_index']}-{_bbox_hash(bbox)}"

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

    return OcrResult(
        document_id=document_id,
        image_url=image_url,
        tokens=token_schemas,
        status=DocumentStatus.ocr_done,
        image_width=image_width,
        image_height=image_height,
    )
