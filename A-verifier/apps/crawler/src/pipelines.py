"""Pipelines Scrapy : normalisation → ingestion DB + ES."""
import logging
import os
import unicodedata

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.services.es_indexer import ESIndexer
from apps.api.src.services.ingest import IngestService
from libs.crawling.fingerprint import compute_fingerprint
from libs.crawling.schemas import RawItem

logger = logging.getLogger(__name__)


class NormalizePipeline:
    """Normalise les titres et calcule le fingerprint — étape légère, synchrone."""

    def process_item(self, item: dict, spider):
        if not item:
            return item
        item["title_norm"] = self._normalize_text(item.get("source_title", ""))
        item["brand_norm"] = self._normalize_text(item.get("brand_raw") or "") or None
        item["fingerprint"] = compute_fingerprint(
            merchant_slug=item["merchant_slug"],
            merchant_sku=item["merchant_sku"],
            condition=item.get("condition", "new"),
        )
        return item

    @staticmethod
    def _normalize_text(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


class PostgresPipeline:
    """Persiste chaque offre via IngestService (normalize → match → upsert DB → ES).

    Méthodes async : Scrapy 2.x avec AsyncioSelectorReactor les gère nativement,
    pas besoin d'un event loop séparé.
    """

    def open_spider(self, spider):
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://app:changeme@postgres:5432/electronic_star",
        )
        es_url = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")

        engine = create_async_engine(db_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._es = AsyncElasticsearch(es_url)

    async def close_spider(self, spider):
        await self._es.close()

    async def process_item(self, item: dict, spider):
        if not item:
            return item
        await self._ingest(item)
        return item

    async def _ingest(self, item: dict) -> None:
        raw = RawItem(**{k: v for k, v in item.items() if k in RawItem.model_fields})
        async with self._session_factory() as session:
            indexer = ESIndexer(self._es)
            svc = IngestService(session, indexer)
            try:
                await svc.ingest(raw)
            except Exception as exc:
                logger.error("Ingest failed for sku=%s: %s", item.get("merchant_sku"), exc)
                await session.rollback()
                raise
