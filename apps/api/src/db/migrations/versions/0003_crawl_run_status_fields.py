"""add crawl run status fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crawl_runs",
        sa.Column("items_scraped", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "crawl_runs",
        sa.Column("ingest_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("crawl_runs", sa.Column("output_path", sa.Text(), nullable=True))
    op.add_column("crawl_runs", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_runs", "error_message")
    op.drop_column("crawl_runs", "output_path")
    op.drop_column("crawl_runs", "ingest_enabled")
    op.drop_column("crawl_runs", "items_scraped")
