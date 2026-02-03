"""create tables

Revision ID: 0001_create_tables
Revises:
Create Date: 2026-02-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_create_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("image_path", sa.String(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("validated_text", sa.Text(), nullable=True),
        sa.Column("structured_fields", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_documents_id", "documents", ["id"])

    op.create_table(
        "tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False),
        sa.Column("token_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_label", sa.String(), nullable=False),
        sa.Column("forced_review", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("line_id", sa.String(), nullable=False),
        sa.Column("bbox", sa.Text(), nullable=False),
        sa.Column("flags", sa.Text(), nullable=False),
    )
    op.create_index("ix_tokens_id", "tokens", ["id"])
    op.create_index("ix_tokens_document_id", "tokens", ["document_id"])

    op.create_table(
        "corrections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("token_id", sa.String(), sa.ForeignKey("tokens.id"), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_corrections_id", "corrections", ["id"])
    op.create_index("ix_corrections_document_id", "corrections", ["document_id"])
    op.create_index("ix_corrections_token_id", "corrections", ["token_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False, server_default="local_user"),
        sa.Column("detail", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_document_id", "audit_logs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_document_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_corrections_token_id", table_name="corrections")
    op.drop_index("ix_corrections_document_id", table_name="corrections")
    op.drop_index("ix_corrections_id", table_name="corrections")
    op.drop_table("corrections")

    op.drop_index("ix_tokens_document_id", table_name="tokens")
    op.drop_index("ix_tokens_id", table_name="tokens")
    op.drop_table("tokens")

    op.drop_index("ix_documents_id", table_name="documents")
    op.drop_table("documents")
