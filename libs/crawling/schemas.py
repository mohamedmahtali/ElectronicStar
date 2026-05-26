from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RawItem(BaseModel):
    """Sortie standardisée d'un spider avant normalisation."""

    merchant_slug: str
    merchant_sku: str
    product_url: str
    source_title: str
    brand_raw: str | None = None
    price_amount: Decimal
    shipping_amount: Decimal = Decimal("0")
    currency: str = "EUR"
    availability: str = "unknown"
    condition: str = "new"
    gtin: str | None = None
    mpn: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    crawled_at: datetime = Field(default_factory=_utc_now)


class ParsedOffer(BaseModel):
    """Offre normalisée prête pour le pipeline match→upsert."""

    merchant_slug: str
    merchant_sku: str
    product_url: str
    title_norm: str
    brand_norm: str | None = None
    price_amount: Decimal
    shipping_amount: Decimal = Decimal("0")
    currency: str = "EUR"
    availability: str = "unknown"
    condition: str = "new"
    gtin: str | None = None
    mpn: str | None = None
    category_path: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = ""
    crawled_at: datetime = Field(default_factory=_utc_now)
