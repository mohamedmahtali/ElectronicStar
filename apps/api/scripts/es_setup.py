"""Run with: python -m apps.api.scripts.es_setup"""
import asyncio

from apps.api.src.search.es_client import get_es_client
from apps.api.src.search.es_mappings import (
    CRAWL_LOGS_TEMPLATE,
    PRODUCTS_INDEX_WRITE,
    PRODUCTS_TEMPLATE,
)


async def setup() -> None:
    es = get_es_client()

    await es.indices.put_index_template(name="products_template", body=PRODUCTS_TEMPLATE)
    print("products_template created")

    await es.indices.put_index_template(name="crawl_logs_template", body=CRAWL_LOGS_TEMPLATE)
    print("crawl_logs_template created")

    if not await es.indices.exists(index=PRODUCTS_INDEX_WRITE):
        await es.indices.create(index=PRODUCTS_INDEX_WRITE)
        print(f"index {PRODUCTS_INDEX_WRITE} created")
    else:
        print(f"index {PRODUCTS_INDEX_WRITE} already exists")

    await es.close()
    print("ES setup complete")


if __name__ == "__main__":
    asyncio.run(setup())
