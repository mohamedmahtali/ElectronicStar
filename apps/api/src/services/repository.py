"""Repository service : implémente DBPort du matcher et gère les upserts PostgreSQL."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import (
    Merchant,
    Offer,
    PriceHistory,
    Product,
    ProductAlias,
    MatchReviewQueue,
)
from libs.crawling.schemas import ParsedOffer
from libs.matcher.engine import DBPort


class ProductRepository(DBPort):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── DBPort (matching) ─────────────────────────────────────────────────────

    async def find_by_gtin(self, gtin: str) -> uuid.UUID | None:
        row = await self._s.execute(select(Product.id).where(Product.gtin == gtin))
        return row.scalar_one_or_none()

    async def find_by_mpn_brand(self, mpn: str, brand_norm: str) -> uuid.UUID | None:
        row = await self._s.execute(
            select(Product.id).where(Product.mpn == mpn, Product.brand_norm == brand_norm)
        )
        return row.scalar_one_or_none()

    async def find_by_known_sku(self, merchant_slug: str, merchant_sku: str) -> uuid.UUID | None:
        stmt = (
            select(ProductAlias.product_id)
            .join(Merchant, Merchant.id == ProductAlias.merchant_id)
            .where(Merchant.slug == merchant_slug, ProductAlias.merchant_sku == merchant_sku)
        )
        row = await self._s.execute(stmt)
        return row.scalar_one_or_none()

    async def find_by_trigram(
        self, brand_norm: str, title_norm: str, category_path: str | None
    ) -> list[tuple[uuid.UUID, float]]:
        # Utilise pg_trgm : similarity() sur brand_norm || ' ' || title_norm
        query = text("""
            SELECT id, similarity(brand_norm || ' ' || title_norm, CAST(:query AS text)) AS score
            FROM products
            WHERE similarity(brand_norm || ' ' || title_norm, CAST(:query AS text)) > 0.3
              AND (CAST(:category AS text) IS NULL OR category_path = CAST(:category AS text))
            ORDER BY score DESC
            LIMIT 5
        """)
        rows = await self._s.execute(
            query,
            {"query": f"{brand_norm} {title_norm}", "category": category_path},
        )
        return [(row.id, float(row.score)) for row in rows]

    async def enqueue_review(self, offer: ParsedOffer, candidates: list[tuple[uuid.UUID, float]]) -> None:
        entry = MatchReviewQueue(
            id=uuid.uuid4(),
            candidate_payload=offer.model_dump(mode="json"),
            candidate_scores={str(pid): score for pid, score in candidates},
        )
        self._s.add(entry)
        await self._s.flush()

    # ── Upsert produit canonique ──────────────────────────────────────────────

    async def get_or_create_product(self, offer: ParsedOffer) -> uuid.UUID:
        canonical_key = _make_canonical_key(offer)
        stmt = select(Product).where(Product.canonical_key == canonical_key)
        result = await self._s.execute(stmt)
        product = result.scalar_one_or_none()
        if product:
            return product.id

        product = Product(
            id=uuid.uuid4(),
            canonical_key=canonical_key,
            brand_norm=offer.brand_norm,
            title_norm=offer.title_norm,
            title_display=offer.title_norm,
            category_path=offer.category_path,
            gtin=offer.gtin,
            mpn=offer.mpn,
            specs=offer.specs,
        )
        self._s.add(product)
        await self._s.flush()
        return product.id

    # ── Upsert alias marchand ─────────────────────────────────────────────────

    async def upsert_alias(
        self, product_id: uuid.UUID, merchant_id: uuid.UUID, offer: ParsedOffer
    ) -> None:
        stmt = pg_insert(ProductAlias).values(
            id=uuid.uuid4(),
            product_id=product_id,
            merchant_id=merchant_id,
            merchant_sku=offer.merchant_sku,
            merchant_product_url=offer.product_url,
            source_title=offer.title_norm,
            brand_raw=offer.brand_norm,
        ).on_conflict_do_update(
            index_elements=["merchant_id", "merchant_sku"],
            set_={
                "merchant_product_url": offer.product_url,
                "source_title": offer.title_norm,
            },
        )
        await self._s.execute(stmt)

    # ── Upsert offre courante ─────────────────────────────────────────────────

    async def upsert_offer(
        self, product_id: uuid.UUID, merchant_id: uuid.UUID, offer: ParsedOffer
    ) -> uuid.UUID:
        now = datetime.now(UTC)
        stmt = pg_insert(Offer).values(
            id=uuid.uuid4(),
            product_id=product_id,
            merchant_id=merchant_id,
            seller_name=None,
            currency=offer.currency,
            price_amount=offer.price_amount,
            shipping_amount=offer.shipping_amount,
            availability=offer.availability,
            condition=offer.condition,
            product_url=offer.product_url,
            fingerprint=offer.fingerprint,
            first_seen_at=now,
            last_seen_at=now,
        ).on_conflict_do_update(
            index_elements=["fingerprint"],
            set_={
                "price_amount": offer.price_amount,
                "shipping_amount": offer.shipping_amount,
                "availability": offer.availability,
                "condition": offer.condition,
                "currency": offer.currency,
                "product_url": offer.product_url,
                "last_seen_at": now,
            },
        ).returning(Offer.id)
        result = await self._s.execute(stmt)
        return result.scalar_one()

    # ── Append price_history ──────────────────────────────────────────────────

    async def append_price_history(self, offer_id: uuid.UUID, offer: ParsedOffer) -> None:
        entry = PriceHistory(
            offer_id=offer_id,
            captured_at=offer.crawled_at,
            price_amount=offer.price_amount,
            shipping_amount=offer.shipping_amount,
            availability=offer.availability,
        )
        self._s.add(entry)

    # ── Merchant lookup ───────────────────────────────────────────────────────

    async def get_merchant_id(self, slug: str) -> uuid.UUID | None:
        row = await self._s.execute(select(Merchant.id).where(Merchant.slug == slug))
        return row.scalar_one_or_none()


def _make_canonical_key(offer: ParsedOffer) -> str:
    if offer.gtin:
        return f"gtin:{offer.gtin}"
    if offer.mpn and offer.brand_norm:
        return f"mpn:{offer.brand_norm}:{offer.mpn}"
    return f"title:{offer.brand_norm or ''}:{offer.title_norm[:80]}"
