"""Pipelines Scrapy : normalisation → ingestion DB + ES."""
import logging
import os
import uuid
import unicodedata
from pathlib import Path

from elasticsearch import AsyncElasticsearch
from scrapy.utils.defer import deferred_from_coro
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.db.models import Merchant, RawDocument
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

        self._engine = create_async_engine(db_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._es = AsyncElasticsearch(es_url)
        self._crawl_run_id = _uuid_or_none(spider.settings.get("CRAWL_RUN_ID"))
        self._raw_documents_enabled = bool(
            spider.settings.getbool("RAW_DOCUMENTS_ENABLED", False)
            and self._crawl_run_id is not None
        )
        self._raw_documents_dir = Path(
            os.getenv(
                "RAW_DOCUMENTS_DIR",
                spider.settings.get("RAW_DOCUMENTS_DIR", "/app/apps/crawler/raw_documents"),
            )
        )

    def close_spider(self, spider):
        return deferred_from_coro(self._close())

    async def _close(self) -> None:
        await self._es.close()
        await self._engine.dispose()

    async def process_item(self, item: dict, spider):
        if not item:
            return item
        raw_document = item.pop("_raw_document", None)
        await self._persist_raw_document(raw_document, item)
        await self._ingest(item)
        return item

    async def _persist_raw_document(self, raw_document: dict | None, item: dict) -> None:
        if not self._raw_documents_enabled or not raw_document:
            return

        body = raw_document.pop("body", b"")
        payload_path = self._write_raw_document_body(raw_document, body)

        async with self._session_factory() as session:
            merchant_id = await session.scalar(
                select(Merchant.id).where(Merchant.slug == item["merchant_slug"])
            )
            if merchant_id is None:
                logger.warning("Raw document ignored for unknown merchant=%s", item["merchant_slug"])
                return

            stmt = pg_insert(RawDocument).values(
                id=uuid.uuid4(),
                crawl_run_id=self._crawl_run_id,
                merchant_id=merchant_id,
                url=raw_document["url"],
                doc_type=raw_document["doc_type"],
                http_status=raw_document["http_status"],
                headers=raw_document["headers"],
                payload_sha256=raw_document["payload_sha256"],
                payload_path=payload_path,
                content_length=raw_document["content_length"],
            ).on_conflict_do_update(
                index_elements=[
                    "crawl_run_id",
                    "merchant_id",
                    "url",
                    "payload_sha256",
                ],
                set_={
                    "http_status": raw_document["http_status"],
                    "headers": raw_document["headers"],
                    "payload_path": payload_path,
                    "content_length": raw_document["content_length"],
                },
            )
            await session.execute(stmt)
            await session.commit()

    def _write_raw_document_body(self, raw_document: dict, body: bytes) -> str:
        run_dir = self._raw_documents_dir / str(self._crawl_run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        extension = _document_extension(raw_document.get("doc_type"))
        path = run_dir / f"{raw_document['payload_sha256']}.{extension}"
        if body and not path.exists():
            path.write_bytes(body)
        return str(path)

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


def _document_extension(doc_type: str | None) -> str:
    if doc_type == "json":
        return "json"
    return "html"


def _uuid_or_none(value) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None
