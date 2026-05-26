import csv
import io
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import CrawlRun, Merchant, Offer, Product, RawDocument
from apps.api.src.db.session import get_db
from apps.api.src.services.freshness import (
    as_utc,
    is_stale,
    offer_stale_after_hours,
    source_age_hours,
)

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


class RawDocumentOut(BaseModel):
    raw_document_id: str
    crawl_run_id: str
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    url: str
    doc_type: str
    http_status: int
    payload_sha256: str
    payload_path: str | None
    content_length: int
    stored_at: str


class RawDocumentsResponse(BaseModel):
    crawl_run_id: str
    documents: list[RawDocumentOut]


class OfferSourceDocumentResponse(BaseModel):
    offer_id: str
    document: RawDocumentOut | None


class StaleOfferOut(BaseModel):
    offer_id: str
    product_id: str
    canonical_key: str
    title: str
    brand: str | None
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    price_amount: float
    shipping_amount: float
    total_amount: float
    availability: str
    product_url: str
    last_seen_at: str
    source_age_hours: float | None


class StaleOffersResponse(BaseModel):
    threshold_hours: float
    total: int
    offers: list[StaleOfferOut]


class OfferAuditOut(BaseModel):
    offer_id: str
    product_id: str
    canonical_key: str
    title: str
    brand: str | None
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    price_amount: float
    shipping_amount: float
    total_amount: float
    availability: str
    product_url: str
    last_seen_at: str
    source_age_hours: float | None
    is_stale: bool
    source_document: RawDocumentOut | None


class OfferAuditResponse(BaseModel):
    total: int
    offers: list[OfferAuditOut]


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


@router.get(
    "/crawl-runs/{crawl_run_id}/documents",
    response_model=RawDocumentsResponse,
)
async def list_crawl_run_documents(
    crawl_run_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows = await _load_raw_documents(db, crawl_run_id=crawl_run_id, limit=limit)
    return RawDocumentsResponse(
        crawl_run_id=str(crawl_run_id),
        documents=_serialize_raw_documents(rows),
    )


@router.get("/offers/stale", response_model=StaleOffersResponse)
async def list_stale_offers(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await _load_stale_offers(db, limit=limit)
    return StaleOffersResponse(
        threshold_hours=offer_stale_after_hours(),
        total=total,
        offers=_serialize_stale_offers(rows),
    )


@router.get("/offers/audit", response_model=OfferAuditResponse)
async def list_offer_audit(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await _load_offer_audit(db, limit=limit)
    return OfferAuditResponse(
        total=total,
        offers=_serialize_offer_audit(rows),
    )


@router.get("/offers/audit.csv")
async def export_offer_audit_csv(
    limit: int = Query(default=500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
):
    rows, _total = await _load_offer_audit(db, limit=limit)
    offers = _serialize_offer_audit(rows)

    return _csv_response(
        filename="electronicstar-offer-audit.csv",
        content=_offer_audit_csv(offers),
    )


@router.get(
    "/offers/{offer_id}/source-document",
    response_model=OfferSourceDocumentResponse,
)
async def get_offer_source_document(
    offer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    offer = await db.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    row = await _load_offer_source_document(db, offer)
    documents = _serialize_raw_documents([row]) if row else []
    return OfferSourceDocumentResponse(
        offer_id=str(offer_id),
        document=documents[0] if documents else None,
    )


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


async def _load_raw_documents(
    db: AsyncSession,
    *,
    crawl_run_id: uuid.UUID,
    limit: int,
) -> list[tuple[RawDocument, Merchant]]:
    result = await db.execute(
        select(RawDocument, Merchant)
        .join(Merchant, Merchant.id == RawDocument.merchant_id)
        .where(RawDocument.crawl_run_id == crawl_run_id)
        .order_by(RawDocument.stored_at.desc(), RawDocument.url)
        .limit(limit)
    )
    return list(result.all())


async def _load_stale_offers(
    db: AsyncSession,
    *,
    limit: int,
) -> tuple[list[tuple[Offer, Product, Merchant]], int]:
    stale_before = datetime.now(UTC) - timedelta(hours=offer_stale_after_hours())
    total_result = await db.execute(
        select(func.count()).select_from(Offer).where(Offer.last_seen_at < stale_before)
    )
    total = int(total_result.scalar_one())

    result = await db.execute(
        select(Offer, Product, Merchant)
        .join(Product, Product.id == Offer.product_id)
        .join(Merchant, Merchant.id == Offer.merchant_id)
        .where(Offer.last_seen_at < stale_before)
        .order_by(Offer.last_seen_at.asc(), Merchant.slug, Product.title_display)
        .limit(limit)
    )
    return list(result.all()), total


async def _load_offer_audit(
    db: AsyncSession,
    *,
    limit: int,
) -> tuple[list[tuple[Offer, Product, Merchant, RawDocument | None]], int]:
    total_result = await db.execute(select(func.count()).select_from(Offer))
    total = int(total_result.scalar_one())

    offers_result = await db.execute(
        select(Offer, Product, Merchant)
        .join(Product, Product.id == Offer.product_id)
        .join(Merchant, Merchant.id == Offer.merchant_id)
        .order_by(Offer.last_seen_at.desc(), Merchant.slug, Product.title_display)
        .limit(limit)
    )

    rows = []
    for offer, product, merchant in offers_result.all():
        source_row = await _load_offer_source_document(db, offer)
        source_document = source_row[0] if source_row else None
        rows.append((offer, product, merchant, source_document))

    return rows, total


async def _load_offer_source_document(
    db: AsyncSession,
    offer: Offer,
) -> tuple[RawDocument, Merchant] | None:
    result = await db.execute(
        select(RawDocument, Merchant)
        .join(Merchant, Merchant.id == RawDocument.merchant_id)
        .where(
            RawDocument.merchant_id == offer.merchant_id,
            RawDocument.url == offer.product_url,
        )
        .order_by(RawDocument.stored_at.desc(), RawDocument.id.desc())
        .limit(1)
    )
    return result.first()


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


def _serialize_raw_documents(
    rows: list[tuple[RawDocument, Merchant]]
) -> list[RawDocumentOut]:
    return [
        RawDocumentOut(
            raw_document_id=str(document.id),
            crawl_run_id=str(document.crawl_run_id),
            merchant_id=str(merchant.id),
            merchant_slug=merchant.slug,
            merchant_name=merchant.display_name,
            url=document.url,
            doc_type=document.doc_type,
            http_status=document.http_status,
            payload_sha256=document.payload_sha256,
            payload_path=document.payload_path,
            content_length=document.content_length,
            stored_at=document.stored_at.isoformat(),
        )
        for document, merchant in rows
    ]


def _serialize_stale_offers(
    rows: list[tuple[Offer, Product, Merchant]]
) -> list[StaleOfferOut]:
    output = []
    for offer, product, merchant in rows:
        last_seen_at = as_utc(offer.last_seen_at)
        price_amount = float(offer.price_amount)
        shipping_amount = float(offer.shipping_amount)
        output.append(
            StaleOfferOut(
                offer_id=str(offer.id),
                product_id=str(product.id),
                canonical_key=product.canonical_key,
                title=product.title_display,
                brand=product.brand_norm,
                merchant_id=str(merchant.id),
                merchant_slug=merchant.slug,
                merchant_name=merchant.display_name,
                price_amount=price_amount,
                shipping_amount=shipping_amount,
                total_amount=price_amount + shipping_amount,
                availability=offer.availability,
                product_url=offer.product_url,
                last_seen_at=last_seen_at.isoformat() if last_seen_at else "",
                source_age_hours=source_age_hours(last_seen_at),
            )
        )
    return output


def _serialize_offer_audit(
    rows: list[tuple[Offer, Product, Merchant, RawDocument | None]]
) -> list[OfferAuditOut]:
    output = []
    for offer, product, merchant, source_document in rows:
        last_seen_at = as_utc(offer.last_seen_at)
        price_amount = float(offer.price_amount)
        shipping_amount = float(offer.shipping_amount)
        serialized_source = (
            _serialize_raw_documents([(source_document, merchant)])[0]
            if source_document
            else None
        )
        output.append(
            OfferAuditOut(
                offer_id=str(offer.id),
                product_id=str(product.id),
                canonical_key=product.canonical_key,
                title=product.title_display,
                brand=product.brand_norm,
                merchant_id=str(merchant.id),
                merchant_slug=merchant.slug,
                merchant_name=merchant.display_name,
                price_amount=price_amount,
                shipping_amount=shipping_amount,
                total_amount=price_amount + shipping_amount,
                availability=offer.availability,
                product_url=offer.product_url,
                last_seen_at=last_seen_at.isoformat() if last_seen_at else "",
                source_age_hours=source_age_hours(last_seen_at),
                is_stale=is_stale(last_seen_at),
                source_document=serialized_source,
            )
        )
    return output


def _offer_audit_csv(offers: list[OfferAuditOut]) -> str:
    return _write_csv(
        [
            "offer_id",
            "product_id",
            "canonical_key",
            "title",
            "brand",
            "merchant_slug",
            "merchant_name",
            "price_amount",
            "shipping_amount",
            "total_amount",
            "availability",
            "product_url",
            "last_seen_at",
            "source_age_hours",
            "is_stale",
            "raw_document_id",
            "crawl_run_id",
            "raw_document_url",
            "raw_document_status",
            "raw_document_path",
            "raw_document_sha256",
            "raw_document_content_length",
            "raw_document_stored_at",
        ],
        [_offer_audit_csv_row(offer) for offer in offers],
    )


def _offer_audit_csv_row(offer: OfferAuditOut) -> list[str]:
    document = offer.source_document
    return [
        offer.offer_id,
        offer.product_id,
        offer.canonical_key,
        offer.title,
        offer.brand or "",
        offer.merchant_slug,
        offer.merchant_name,
        f"{offer.price_amount:.2f}",
        f"{offer.shipping_amount:.2f}",
        f"{offer.total_amount:.2f}",
        offer.availability,
        offer.product_url,
        offer.last_seen_at,
        f"{offer.source_age_hours:.3f}" if offer.source_age_hours is not None else "",
        str(offer.is_stale).lower(),
        document.raw_document_id if document else "",
        document.crawl_run_id if document else "",
        document.url if document else "",
        str(document.http_status) if document else "",
        document.payload_path if document and document.payload_path else "",
        document.payload_sha256 if document else "",
        str(document.content_length) if document else "",
        document.stored_at if document else "",
    ]


def _duration_seconds(started_at: datetime, ended_at: datetime | None) -> float | None:
    if ended_at is None:
        return None
    return round((ended_at - started_at).total_seconds(), 3)


def _write_csv(headers: list[str], rows: list[list[str]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([_sanitize_csv_row(row) for row in rows])
    return output.getvalue()


def _sanitize_csv_row(row: list[str]) -> list[str]:
    return [_sanitize_csv_cell(cell) for cell in row]


def _sanitize_csv_cell(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _csv_response(filename: str, content: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
