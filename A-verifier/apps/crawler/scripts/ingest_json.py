"""Ingest a previously exported Scrapy JSON feed.

Usage inside the crawler container:
python -m apps.crawler.scripts.ingest_json /app/apps/crawler/ldlc_test.json
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.services.es_indexer import ESIndexer
from apps.api.src.services.ingest import IngestService
from libs.crawling.schemas import RawItem


async def ingest_file(path: Path) -> None:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:changeme@postgres:5432/electronic_star",
    )
    es_url = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")

    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list in {path}")

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    es = AsyncElasticsearch(es_url)

    ingested = 0
    try:
        async with session_factory() as session:
            service = IngestService(session, ESIndexer(es))
            for row in payload:
                await service.ingest(RawItem(**row))
                ingested += 1
    finally:
        await es.close()
        await engine.dispose()

    print(f"Ingested {ingested} items from {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    asyncio.run(ingest_file(args.path))


if __name__ == "__main__":
    main()
