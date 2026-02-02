from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    image_path = Column(String, nullable=False)
    image_width = Column(Integer, nullable=False)
    image_height = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    validated_text = Column(Text, nullable=True)
    structured_fields = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Token(Base):
    __tablename__ = "tokens"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), index=True, nullable=False)
    line_index = Column(Integer, nullable=False)
    token_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    confidence_label = Column(String, nullable=False)
    forced_review = Column(Boolean, default=False, nullable=False)
    line_id = Column(String, nullable=False)
    bbox = Column(Text, nullable=False)
    flags = Column(Text, nullable=False)


class Correction(Base):
    __tablename__ = "corrections"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), index=True, nullable=False)
    token_id = Column(String, ForeignKey("tokens.id"), index=True, nullable=False)
    original_text = Column(Text, nullable=False)
    corrected_text = Column(Text, nullable=False)
    confirmed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), index=True, nullable=False)
    event_type = Column(String, nullable=False)
    actor = Column(String, nullable=False, default="local_user")
    detail = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
