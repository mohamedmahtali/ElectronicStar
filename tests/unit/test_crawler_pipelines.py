import asyncio

import pytest

from apps.crawler.src.pipelines import PostgresPipeline


class _FakeES:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_postgres_pipeline_close_spider_closes_async_resources():
    pipeline = PostgresPipeline()
    pipeline._es = _FakeES()
    pipeline._engine = _FakeEngine()

    deferred = pipeline.close_spider(spider=None)
    await deferred.asFuture(asyncio.get_running_loop())

    assert pipeline._es.closed is True
    assert pipeline._engine.disposed is True
