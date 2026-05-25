from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import CrawlRun, Merchant
from apps.api.src.db.session import get_db

router = APIRouter(prefix="/ops", tags=["ops"])


class CrawlRunOut(BaseModel):
    crawl_run_id: str
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    run_type: str
    status: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    items_scraped: int
    pages_ok: int
    pages_failed: int
    captcha_count: int
    blocked_count: int
    ingest_enabled: bool
    output_path: str | None
    error_message: str | None


class CrawlRunsResponse(BaseModel):
    runs: list[CrawlRunOut]


@router.get("/crawl-runs", response_model=CrawlRunsResponse)
async def list_crawl_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows = await _load_crawl_runs(db, limit=limit)
    return CrawlRunsResponse(runs=_serialize_crawl_runs(rows))


@router.get("/crawl-runs/latest", response_model=CrawlRunsResponse)
async def list_latest_crawl_runs(db: AsyncSession = Depends(get_db)):
    rows = await _load_crawl_runs(db, limit=100)
    latest_by_merchant: dict[str, tuple[CrawlRun, Merchant]] = {}

    for run, merchant in rows:
        latest_by_merchant.setdefault(merchant.slug, (run, merchant))

    latest_rows = [latest_by_merchant[slug] for slug in sorted(latest_by_merchant)]
    return CrawlRunsResponse(runs=_serialize_crawl_runs(latest_rows))


async def _load_crawl_runs(
    db: AsyncSession,
    *,
    limit: int,
) -> list[tuple[CrawlRun, Merchant]]:
    result = await db.execute(
        select(CrawlRun, Merchant)
        .join(Merchant, Merchant.id == CrawlRun.merchant_id)
        .order_by(CrawlRun.started_at.desc())
        .limit(limit)
    )
    return list(result.all())


def _serialize_crawl_runs(rows: list[tuple[CrawlRun, Merchant]]) -> list[CrawlRunOut]:
    return [
        CrawlRunOut(
            crawl_run_id=str(run.id),
            merchant_id=str(merchant.id),
            merchant_slug=merchant.slug,
            merchant_name=merchant.display_name,
            run_type=run.run_type,
            status=run.status,
            started_at=run.started_at.isoformat(),
            ended_at=run.ended_at.isoformat() if run.ended_at else None,
            duration_seconds=_duration_seconds(run.started_at, run.ended_at),
            items_scraped=run.items_scraped,
            pages_ok=run.pages_ok,
            pages_failed=run.pages_failed,
            captcha_count=run.captcha_count,
            blocked_count=run.blocked_count,
            ingest_enabled=run.ingest_enabled,
            output_path=run.output_path,
            error_message=run.error_message,
        )
        for run, merchant in rows
    ]


def _duration_seconds(started_at: datetime, ended_at: datetime | None) -> float | None:
    if ended_at is None:
        return None
    return round((ended_at - started_at).total_seconds(), 3)
