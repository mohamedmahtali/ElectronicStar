"""Service d'ingestion : normalise → matche → upsert DB → indexe ES."""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.services.repository import ProductRepository
from apps.api.src.services.es_indexer import ESIndexer
from libs.crawling.fingerprint import compute_fingerprint
from libs.crawling.schemas import ParsedOffer, RawItem
from libs.matcher.engine import MatchEngine
from libs.normalizer import normalize_brand, normalize_category, normalize_title

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self, session: AsyncSession, indexer: ESIndexer) -> None:
        self._repo = ProductRepository(session)
        self._session = session
        self._matcher = MatchEngine(self._repo)
        self._indexer = indexer

    async def ingest(self, raw: RawItem) -> None:
        offer = self._normalize(raw)

        merchant_id = await self._repo.get_merchant_id(offer.merchant_slug)
        if not merchant_id:
            logger.warning("Marchand inconnu : %s — item ignoré", offer.merchant_slug)
            return

        match = await self._matcher.match(offer)

        if match.needs_review:
            logger.info("match=review_queue sku=%s confidence=%.2f", offer.merchant_sku, match.confidence)
            await self._session.commit()
            return

        product_id: uuid.UUID = match.product_id or await self._repo.get_or_create_product(offer)

        await self._repo.upsert_alias(product_id, merchant_id, offer)
        offer_id = await self._repo.upsert_offer(product_id, merchant_id, offer)
        await self._repo.append_price_history(offer_id, offer)

        await self._session.commit()

        await self._indexer.index_product(product_id, self._repo)

        logger.info(
            "ingested strategy=%s product=%s merchant=%s sku=%s price=%s",
            match.strategy, product_id, offer.merchant_slug, offer.merchant_sku, offer.price_amount,
        )

    @staticmethod
    def _normalize(raw: RawItem) -> ParsedOffer:
        title_norm = normalize_title(raw.source_title)
        brand_norm = normalize_brand(raw.brand_raw)
        category_path = normalize_category(raw.source_title)

        fingerprint = compute_fingerprint(
            merchant_slug=raw.merchant_slug,
            merchant_sku=raw.merchant_sku,
            condition=raw.condition,
        )

        return ParsedOffer(
            merchant_slug=raw.merchant_slug,
            merchant_sku=raw.merchant_sku,
            product_url=raw.product_url,
            title_norm=title_norm,
            brand_norm=brand_norm,
            price_amount=raw.price_amount,
            shipping_amount=raw.shipping_amount,
            currency=raw.currency,
            availability=raw.availability,
            condition=raw.condition,
            gtin=raw.gtin,
            mpn=raw.mpn,
            category_path=category_path,
            specs=raw.specs,
            fingerprint=fingerprint,
            crawled_at=raw.crawled_at,
        )
