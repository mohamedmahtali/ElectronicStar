import os

from elasticsearch import AsyncElasticsearch

_client: AsyncElasticsearch | None = None


def get_es_client() -> AsyncElasticsearch:
    global _client
    if _client is None:
        url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
        _client = AsyncElasticsearch(url)
    return _client


async def close_es_client() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None
