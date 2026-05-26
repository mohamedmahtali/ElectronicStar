"""add raw document payload metadata

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("raw_documents", sa.Column("payload_path", sa.Text(), nullable=True))
    op.add_column(
        "raw_documents",
        sa.Column("content_length", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_constraint(
        "raw_documents_merchant_id_url_payload_sha256_key",
        "raw_documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_raw_documents_run_merchant_url_payload",
        "raw_documents",
        ["crawl_run_id", "merchant_id", "url", "payload_sha256"],
    )
    op.create_index(
        "ix_raw_documents_crawl_run_stored",
        "raw_documents",
        ["crawl_run_id", "stored_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_documents_crawl_run_stored", table_name="raw_documents")
    op.drop_constraint(
        "uq_raw_documents_run_merchant_url_payload",
        "raw_documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "raw_documents_merchant_id_url_payload_sha256_key",
        "raw_documents",
        ["merchant_id", "url", "payload_sha256"],
    )
    op.drop_column("raw_documents", "content_length")
    op.drop_column("raw_documents", "payload_path")
