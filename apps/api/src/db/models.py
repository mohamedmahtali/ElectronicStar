import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="FR")
    crawl_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("slug"),
        Index("ix_merchants_crawl_policy", "crawl_policy", postgresql_using="gin"),
    )


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)  # full | incremental
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    pages_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    captcha_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_crawl_runs_merchant_started", "merchant_id", "started_at"),
    )


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_runs.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)  # html | json
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("merchant_id", "url", "payload_sha256"),
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_key: Mapped[str] = mapped_column(String(256), nullable=False)
    brand_norm: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title_norm: Mapped[str] = mapped_column(Text, nullable=False)
    title_display: Mapped[str] = mapped_column(Text, nullable=False)
    category_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    mpn: Mapped[str | None] = mapped_column(String(128), nullable=True)
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Populated by trigger or application code
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list["ProductAlias"]] = relationship(back_populates="product")
    offers: Mapped[list["Offer"]] = relationship(back_populates="product")

    __table_args__ = (
        UniqueConstraint("canonical_key"),
        Index("ix_products_gtin", "gtin"),
        Index("ix_products_specs", "specs", postgresql_using="gin"),
        Index("ix_products_search_tsv", "search_tsv", postgresql_using="gin"),
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    merchant_sku: Mapped[str] = mapped_column(String(256), nullable=False)
    merchant_product_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_raw: Mapped[str | None] = mapped_column(String(256), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("merchant_id", "merchant_sku"),
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("merchants.id"), nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    price_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    availability: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="offers")

    __table_args__ = (
        UniqueConstraint("fingerprint"),
        Index("ix_offers_product_merchant", "product_id", "merchant_id"),
    )


class PriceHistory(Base):
    """Partitioned by month on captured_at."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    price_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    availability: Mapped[str] = mapped_column(String(32), nullable=False)
    stock_text: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_price_history_offer_captured", "offer_id", "captured_at"),
    )


class MatchReviewQueue(Base):
    __tablename__ = "match_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    candidate_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)  # approved | rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_match_review_decision", "decision", "reviewed_at"),
    )
