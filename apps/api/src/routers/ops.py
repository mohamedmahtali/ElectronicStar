import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import PurePosixPath

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import CrawlRun, Merchant
from apps.api.src.db.session import get_db

DEFAULT_REQUEST_QUEUE = "crawler:run_requests"


def require_ops_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected_token = os.getenv("OPS_ADMIN_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPS_ADMIN_TOKEN non configure",
        )

    if x_admin_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token admin requis",
        )

    if not secrets.compare_digest(x_admin_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token admin invalide",
        )


router = APIRouter(
    prefix="/ops",
    tags=["ops"],
    dependencies=[Depends(require_ops_admin_token)],
)


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


class CrawlRunTriggerResponse(BaseModel):
    crawl_run_id: str
    merchant_slug: str
    status: str
    queued: bool


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


@router.post(
    "/crawl-runs/{merchant_slug}/run",
    response_model=CrawlRunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_crawl_run(
    merchant_slug: str,
    itemcount: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    merchant = await _load_merchant(db, merchant_slug)
    crawl_run_id = uuid.uuid4()
    output_path = _manual_output_path(merchant.slug, crawl_run_id)

    run = CrawlRun(
        id=crawl_run_id,
        merchant_id=merchant.id,
        run_type="manual",
        status="queued",
        ingest_enabled=True,
        output_path=output_path,
    )
    db.add(run)
    await db.commit()

    payload = {
        "crawl_run_id": str(crawl_run_id),
        "merchant": merchant.slug,
        "itemcount": itemcount,
        "ingest": True,
        "output": output_path,
        "log_level": os.getenv("CRAWLER_LOG_LEVEL", "INFO"),
    }

    try:
        await _enqueue_crawl_request(payload, merchant.slug)
    except RedisError as exc:
        await _mark_run_failed(db, crawl_run_id, f"RedisError: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File Redis indisponible",
        ) from exc

    return CrawlRunTriggerResponse(
        crawl_run_id=str(crawl_run_id),
        merchant_slug=merchant.slug,
        status="queued",
        queued=True,
    )


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


async def _load_merchant(db: AsyncSession, merchant_slug: str) -> Merchant:
    result = await db.execute(select(Merchant).where(Merchant.slug == merchant_slug))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Marchand introuvable")
    return merchant


async def _enqueue_crawl_request(payload: dict, merchant_slug: str) -> None:
    client = redis.Redis.from_url(_redis_url(), decode_responses=True)
    try:
        await client.rpush(_request_queue(merchant_slug), json.dumps(payload))
    finally:
        await client.aclose()


async def _mark_run_failed(
    db: AsyncSession,
    crawl_run_id: uuid.UUID,
    error_message: str,
) -> None:
    run = await db.get(CrawlRun, crawl_run_id)
    if run is None:
        return
    run.status = "failed"
    run.ended_at = datetime.now().astimezone()
    run.error_message = error_message
    await db.commit()


def _manual_output_path(merchant_slug: str, crawl_run_id: uuid.UUID) -> str:
    return str(
        PurePosixPath("/app/apps/crawler/scheduled")
        / f"{merchant_slug}_manual_{str(crawl_run_id)[:8]}.json"
    )


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


def _request_queue(merchant_slug: str | None = None) -> str:
    base_queue = os.getenv("CRAWLER_REQUEST_QUEUE", DEFAULT_REQUEST_QUEUE).strip()
    if not base_queue:
        base_queue = DEFAULT_REQUEST_QUEUE

    if merchant_slug is None:
        return base_queue

    env_name = f"CRAWLER_{merchant_slug.upper().replace('-', '_')}_REQUEST_QUEUE"
    merchant_queue = os.getenv(env_name, "").strip()
    if merchant_queue:
        return merchant_queue
    return f"{base_queue}:{merchant_slug}"


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
