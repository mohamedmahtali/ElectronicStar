"""add default price_history partition

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history_default
        PARTITION OF price_history DEFAULT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS price_history_default")
