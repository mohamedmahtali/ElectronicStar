import json
import os
from decimal import Decimal
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"


@pytest.mark.asyncio
async def test_ingest_fixtures_end_to_end():
    if os.getenv("RUN_INGEST_INTEGRATION") != "1":
        pytest.skip("set RUN_INGEST_INTEGRATION=1 to run destructive DB/ES integration test")

    pytest.importorskip("asyncpg")
    pytest.importorskip("elasticsearch")
    pytest.importorskip("sqlalchemy")

    from elasticsearch import AsyncElasticsearch
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from apps.api.src.db.models import Merchant
    from apps.api.src.search.es_mappings import PRODUCTS_INDEX_WRITE, PRODUCTS_TEMPLATE
    from apps.api.src.services.es_indexer import ESIndexer
    from apps.api.src.services.ingest import IngestService
    from libs.crawling.schemas import RawItem

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:changeme@localhost:5432/electronic_star",
    )
    es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

    engine = create_async_engine(db_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    es = AsyncElasticsearch(es_url)

    try:
        await _reset_es(es, PRODUCTS_INDEX_WRITE, PRODUCTS_TEMPLATE)

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    TRUNCATE TABLE
                        price_history,
                        offers,
                        product_aliases,
                        match_review_queue,
                        products,
                        merchants
                    RESTART IDENTITY CASCADE
                    """
                )
            )

        async with session_factory() as session:
            await _seed_merchants(session, Merchant, pg_insert)
            await session.commit()

        async with session_factory() as session:
            service = IngestService(session, ESIndexer(es))
            for fixture in ("ldlc.json", "materiel.json", "ldlc_price_change.json"):
                for row in _load_fixture(fixture):
                    await service.ingest(RawItem(**row))

        await es.indices.refresh(index=PRODUCTS_INDEX_WRITE)

        async with session_factory() as session:
            counts = await _table_counts(session)
            current_price = await _current_offer_price(session, "ldlc", "AR202602240108")
            canonical_product_id = await _canonical_product_id(
                session, "gtin:0199271991237"
            )
            canonical_offer_count = await _canonical_offer_count(session, "gtin:0199271991237")
            product_detail_response = await _get_product_detail(
                canonical_product_id, session
            )
            price_history_response = await _get_price_history_response(
                canonical_product_id, session
            )
            offers_response = await _get_offers_response(canonical_product_id, session)
            lenovo_search_response = await _search_products(session, es, "lenovo")
            xiaomi_ldlc_response = await _search_products(
                session, es, "xiaomi", merchant="ldlc"
            )
            xiaomi_materiel_response = await _search_products(
                session, es, "xiaomi", merchant="materiel"
            )

        assert counts == {
            "merchants": 2,
            "products": 4,
            "offers": 5,
            "price_history": 6,
            "match_review_queue": 0,
        }
        assert current_price == Decimal("499.95")
        assert canonical_offer_count == 2
        assert product_detail_response.canonical_key == "gtin:0199271991237"
        assert product_detail_response.price_min == 499.95
        assert product_detail_response.price_max == 499.95
        assert {
            merchant.merchant_slug
            for merchant in product_detail_response.merchants
        } == {"ldlc", "materiel"}
        assert len(product_detail_response.offers) == 2
        assert len(price_history_response.points) == 3
        assert {point.merchant_slug for point in price_history_response.points} == {
            "ldlc",
            "materiel",
        }
        assert [
            point.price_amount
            for point in price_history_response.points
            if point.merchant_slug == "ldlc"
        ] == [499.95, 499.95]
        assert min(point.total_amount for point in price_history_response.points) == 499.95
        assert {offer.merchant_slug for offer in offers_response.offers} == {"ldlc", "materiel"}
        assert {offer.merchant_name for offer in offers_response.offers} == {"LDLC", "Materiel.net"}
        assert lenovo_search_response.total == 1
        assert {
            merchant.merchant_slug
            for merchant in lenovo_search_response.items[0].merchants
        } == {"ldlc", "materiel"}
        assert xiaomi_ldlc_response.total == 0
        assert xiaomi_materiel_response.total == 2

        es_count = await es.count(index=PRODUCTS_INDEX_WRITE)
        assert es_count["count"] == 4
        lenovo_doc = await _get_es_doc_by_canonical_key(es, PRODUCTS_INDEX_WRITE, "gtin:0199271991237")
        assert lenovo_doc["price_min"] == 499.95
        assert lenovo_doc["price_max"] == 499.95
        assert len(lenovo_doc["merchant_ids"]) == 2
        assert len(lenovo_doc["offers"]) == 2
    finally:
        await es.close()
        await engine.dispose()


def _load_fixture(name: str) -> list[dict]:
    payload = json.loads((FIXTURE_DIR / name).read_text())
    assert isinstance(payload, list)
    return payload


async def _reset_es(es, products_index: str, products_template: dict) -> None:
    await es.indices.put_index_template(name="products_template", body=products_template)
    await es.options(ignore_status=[404]).indices.delete(index=products_index)
    await es.indices.create(index=products_index)


async def _seed_merchants(session, Merchant, pg_insert) -> None:
    rows = [
        {
            "slug": "ldlc",
            "display_name": "LDLC",
            "base_url": "https://www.ldlc.com",
            "country_code": "FR",
            "crawl_policy": {"delay": 2.0, "concurrency": 1},
        },
        {
            "slug": "materiel",
            "display_name": "Materiel.net",
            "base_url": "https://www.materiel.net",
            "country_code": "FR",
            "crawl_policy": {"delay": 2.0, "concurrency": 1},
        },
    ]
    await session.execute(
        pg_insert(Merchant)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["slug"])
    )


async def _table_counts(session) -> dict[str, int]:
    from sqlalchemy import text

    counts = {}
    for table_name in ("merchants", "products", "offers", "price_history", "match_review_queue"):
        result = await session.execute(text(f"SELECT count(*) FROM {table_name}"))
        counts[table_name] = result.scalar_one()
    return counts


async def _current_offer_price(session, merchant_slug: str, merchant_sku: str) -> Decimal:
    from sqlalchemy import text

    result = await session.execute(
        text(
            """
            SELECT o.price_amount
            FROM offers o
            JOIN merchants m ON m.id = o.merchant_id
            JOIN product_aliases pa
              ON pa.product_id = o.product_id
             AND pa.merchant_id = o.merchant_id
            WHERE m.slug = :merchant_slug
              AND pa.merchant_sku = :merchant_sku
            """
        ),
        {"merchant_slug": merchant_slug, "merchant_sku": merchant_sku},
    )
    return result.scalar_one()


async def _canonical_offer_count(session, canonical_key: str) -> int:
    from sqlalchemy import text

    result = await session.execute(
        text(
            """
            SELECT count(*)
            FROM offers o
            JOIN products p ON p.id = o.product_id
            WHERE p.canonical_key = :canonical_key
            """
        ),
        {"canonical_key": canonical_key},
    )
    return result.scalar_one()


async def _canonical_product_id(session, canonical_key: str):
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT id FROM products WHERE canonical_key = :canonical_key"),
        {"canonical_key": canonical_key},
    )
    return result.scalar_one()


async def _get_offers_response(product_id, session):
    from apps.api.src.routers.products import get_product_offers

    return await get_product_offers(product_id, session)


async def _get_product_detail(product_id, session):
    from apps.api.src.routers.products import get_product_detail

    return await get_product_detail(product_id, session)


async def _get_price_history_response(product_id, session):
    from apps.api.src.routers.products import get_product_price_history

    return await get_product_price_history(product_id, session)


async def _search_products(session, es, q: str, merchant: str | None = None):
    from apps.api.src.routers.search import search_products

    return await search_products(
        q=q,
        merchant=merchant,
        page=1,
        size=5,
        es=es,
        db=session,
    )


async def _get_es_doc_by_canonical_key(es, index_name: str, canonical_key: str) -> dict:
    result = await es.search(
        index=index_name,
        query={"term": {"canonical_key": canonical_key}},
        size=1,
    )
    hits = result["hits"]["hits"]
    assert len(hits) == 1
    return hits[0]["_source"]
