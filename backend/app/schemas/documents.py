from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    ocr_done = "ocr_done"
    review_in_progress = "review_in_progress"
    validated = "validated"
    summarized = "summarized"
    exported = "exported"


class TokenConfidenceLabel(str, Enum):
    trusted = "trusted"
    medium = "medium"
    low = "low"


class TokenSchema(BaseModel):
    id: str
    line_id: str
    line_index: int
    token_index: int
    text: str
    confidence: float
    confidence_label: TokenConfidenceLabel
    forced_review: bool
    bbox: tuple[float, float, float, float]
    flags: list[str]


class UploadResponse(BaseModel):
    document_id: str
    image_url: str
    image_width: int
    image_height: int
    status: DocumentStatus
    tokens: list[TokenSchema]


class CorrectionSchema(BaseModel):
    token_id: str
    corrected_text: str


class ValidateRequest(BaseModel):
    corrections: list[CorrectionSchema] = Field(default_factory=list)
    reviewed_token_ids: list[str] = Field(default_factory=list)
    review_complete: bool = False


class ValidateResponse(BaseModel):
    validated_text: str
    validation_status: DocumentStatus
    validated_at: datetime | None = None


class SummaryResponse(BaseModel):
    bullet_summary: list[str]
    structured_fields: dict[str, str]
    validation_status: DocumentStatus
