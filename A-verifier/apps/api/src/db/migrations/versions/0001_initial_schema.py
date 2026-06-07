"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="FR"),
        sa.Column("crawl_policy", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_merchants_crawl_policy", "merchants", ["crawl_policy"], postgresql_using="gin")

    op.create_table(
        "crawl_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("pages_ok", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("captcha_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_crawl_runs_merchant_started", "crawl_runs", ["merchant_id", "started_at"])

    op.create_table(
        "raw_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("crawl_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("crawl_runs.id"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=False),
        sa.Column("headers", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("merchant_id", "url", "payload_sha256"),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_key", sa.String(256), nullable=False),
        sa.Column("brand_norm", sa.String(256), nullable=True),
        sa.Column("title_norm", sa.Text, nullable=False),
        sa.Column("title_display", sa.Text, nullable=False),
        sa.Column("category_path", sa.Text, nullable=True),
        sa.Column("gtin", sa.String(14), nullable=True),
        sa.Column("mpn", sa.String(128), nullable=True),
        sa.Column("specs", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("search_tsv", postgresql.TSVECTOR, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("canonical_key"),
    )
    op.create_index("ix_products_gtin", "products", ["gtin"])
    op.create_index("ix_products_specs", "products", ["specs"], postgresql_using="gin")
    op.create_index("ix_products_search_tsv", "products", ["search_tsv"], postgresql_using="gin")

    # Trigger to auto-update search_tsv
    op.execute("""
        CREATE OR REPLACE FUNCTION products_search_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_tsv := to_tsvector('french',
                coalesce(NEW.brand_norm, '') || ' ' ||
                coalesce(NEW.title_norm, '') || ' ' ||
                coalesce(NEW.mpn, '')
            );
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER products_tsv_trigger
        BEFORE INSERT OR UPDATE ON products
        FOR EACH ROW EXECUTE FUNCTION products_search_tsv_update();
    """)

    op.create_table(
        "product_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("merchant_sku", sa.String(256), nullable=False),
        sa.Column("merchant_product_url", sa.Text, nullable=False),
        sa.Column("source_title", sa.Text, nullable=True),
        sa.Column("brand_raw", sa.String(256), nullable=True),
        sa.UniqueConstraint("merchant_id", "merchant_sku"),
    )

    op.create_table(
        "offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("seller_name", sa.String(256), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("availability", sa.String(32), nullable=False),
        sa.Column("condition", sa.String(16), nullable=False, server_default="new"),
        sa.Column("product_url", sa.Text, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_offers_product_merchant", "offers", ["product_id", "merchant_id"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger, autoincrement=True, nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("availability", sa.String(32), nullable=False),
        sa.Column("stock_text", sa.String(256), nullable=True),
        sa.PrimaryKeyConstraint("id", "captured_at"),
        postgresql_partition_by="RANGE (captured_at)",
    )
    op.create_index("ix_price_history_offer_captured", "price_history", ["offer_id", "captured_at"])

    op.create_table(
        "match_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_payload", postgresql.JSONB, nullable=False),
        sa.Column("candidate_scores", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_match_review_decision", "match_review_queue", ["decision", "reviewed_at"])


def downgrade() -> None:
    op.drop_table("match_review_queue")
    op.drop_table("price_history")
    op.drop_table("offers")
    op.drop_table("product_aliases")
    op.execute("DROP TRIGGER IF EXISTS products_tsv_trigger ON products")
    op.execute("DROP FUNCTION IF EXISTS products_search_tsv_update")
    op.drop_table("products")
    op.drop_table("raw_documents")
    op.drop_table("crawl_runs")
    op.drop_table("merchants")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
