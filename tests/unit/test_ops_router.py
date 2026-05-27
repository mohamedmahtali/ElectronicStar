import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api.main import app
from apps.api.src.routers.ops import (
    _offer_audit_csv,
    _manual_output_path,
    _price_warning,
    _request_queue,
    _serialize_offer_audit,
    _serialize_crawl_runs,
    _serialize_raw_documents,
    _serialize_stale_offers,
    require_ops_admin_token,
)


def test_serialize_crawl_runs_includes_status_metrics():
    started_at = datetime(2026, 5, 25, 2, 56, tzinfo=UTC)
    ended_at = started_at + timedelta(seconds=62.523)
    run = SimpleNamespace(
        id=uuid.uuid4(),
        run_type="full",
        status="success",
        started_at=started_at,
        ended_at=ended_at,
        items_scraped=21,
        pages_ok=26,
        pages_failed=0,
        captcha_count=0,
        blocked_count=0,
        ingest_enabled=True,
        output_path="/app/apps/crawler/materiel_crawl_ingest.json",
        error_message=None,
    )
    merchant = SimpleNamespace(
        id=uuid.uuid4(),
        slug="materiel",
        display_name="Materiel.net",
    )

    serialized = _serialize_crawl_runs([(run, merchant)])

    assert len(serialized) == 1
    item = serialized[0]
    assert item.crawl_run_id == str(run.id)
    assert item.merchant_slug == "materiel"
    assert item.status == "success"
    assert item.items_scraped == 21
    assert item.duration_seconds == 62.523
    assert item.ingest_enabled is True
    assert item.error_message is None


def test_manual_output_path_uses_crawl_run_prefix():
    crawl_run_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    assert _manual_output_path("materiel", crawl_run_id) == (
        "/app/apps/crawler/scheduled/materiel_manual_12345678.json"
    )


def test_serialize_raw_documents_includes_payload_metadata():
    crawl_run_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    stored_at = datetime(2026, 5, 26, 10, 15, tzinfo=UTC)
    document = SimpleNamespace(
        id=uuid.uuid4(),
        crawl_run_id=crawl_run_id,
        merchant_id=merchant_id,
        url="https://www.ldlc.com/fiche/PB00728588.html",
        doc_type="html",
        http_status=200,
        payload_sha256="a" * 64,
        payload_path="/app/apps/crawler/raw_documents/run/a.html",
        content_length=12345,
        stored_at=stored_at,
    )
    merchant = SimpleNamespace(
        id=merchant_id,
        slug="ldlc",
        display_name="LDLC",
    )

    serialized = _serialize_raw_documents([(document, merchant)])

    assert len(serialized) == 1
    item = serialized[0]
    assert item.raw_document_id == str(document.id)
    assert item.crawl_run_id == str(crawl_run_id)
    assert item.merchant_slug == "ldlc"
    assert item.url == document.url
    assert item.payload_path == document.payload_path
    assert item.content_length == 12345
    assert item.stored_at == stored_at.isoformat()


def test_serialize_stale_offers_includes_refresh_metadata():
    product_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    last_seen_at = datetime(2026, 5, 25, 8, 30, tzinfo=UTC)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        product_id=product_id,
        merchant_id=merchant_id,
        price_amount=Decimal("499.95"),
        shipping_amount=Decimal("0"),
        availability="in_stock",
        product_url="https://www.ldlc.com/fiche/PB00728588.html",
        last_seen_at=last_seen_at,
    )
    product = SimpleNamespace(
        id=product_id,
        canonical_key="gtin:0199271991237",
        title_display="Lenovo V15 G5 IRL (83GW007KFR)",
        brand_norm="lenovo",
    )
    merchant = SimpleNamespace(
        id=merchant_id,
        slug="ldlc",
        display_name="LDLC",
    )

    serialized = _serialize_stale_offers([(offer, product, merchant)])

    assert len(serialized) == 1
    item = serialized[0]
    assert item.offer_id == str(offer.id)
    assert item.product_id == str(product_id)
    assert item.canonical_key == "gtin:0199271991237"
    assert item.merchant_slug == "ldlc"
    assert item.total_amount == 499.95
    assert item.last_seen_at == last_seen_at.isoformat()
    assert item.source_age_hours is not None


def test_serialize_offer_audit_includes_price_and_source_document():
    product_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    crawl_run_id = uuid.uuid4()
    last_seen_at = datetime(2026, 5, 26, 8, 30, tzinfo=UTC)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        product_id=product_id,
        merchant_id=merchant_id,
        price_amount=Decimal("499.95"),
        shipping_amount=Decimal("0"),
        availability="in_stock",
        product_url="https://www.ldlc.com/fiche/PB00728588.html",
        last_seen_at=last_seen_at,
    )
    product = SimpleNamespace(
        id=product_id,
        canonical_key="gtin:0199271991237",
        title_display="Lenovo V15 G5 IRL (83GW007KFR)",
        brand_norm="lenovo",
    )
    merchant = SimpleNamespace(
        id=merchant_id,
        slug="ldlc",
        display_name="LDLC",
    )
    source_document = SimpleNamespace(
        id=uuid.uuid4(),
        crawl_run_id=crawl_run_id,
        merchant_id=merchant_id,
        url=offer.product_url,
        doc_type="html",
        http_status=200,
        payload_sha256="b" * 64,
        payload_path="/app/apps/crawler/raw_documents/run/b.html",
        content_length=23456,
        stored_at=last_seen_at,
    )

    serialized = _serialize_offer_audit([(offer, product, merchant, source_document)])

    assert len(serialized) == 1
    item = serialized[0]
    assert item.offer_id == str(offer.id)
    assert item.product_id == str(product_id)
    assert item.total_amount == 499.95
    assert item.last_seen_at == last_seen_at.isoformat()
    assert item.source_document is not None
    assert item.source_document.raw_document_id == str(source_document.id)
    assert item.source_document.payload_path == source_document.payload_path
    assert item.price_warning == "ok"


def test_serialize_offer_audit_flags_large_price_gap():
    product_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    last_seen_at = datetime(2026, 5, 26, 8, 30, tzinfo=UTC)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        product_id=product_id,
        merchant_id=merchant_id,
        price_amount=Decimal("399.95"),
        shipping_amount=Decimal("0"),
        availability="in_stock",
        product_url="https://www.ldlc.com/fiche/PB00728588.html",
        last_seen_at=last_seen_at,
    )
    product = SimpleNamespace(
        id=product_id,
        canonical_key="gtin:0199271991237",
        title_display="Lenovo V15 G5 IRL (83GW007KFR)",
        brand_norm="lenovo",
    )
    merchant = SimpleNamespace(
        id=merchant_id,
        slug="ldlc",
        display_name="LDLC",
    )
    source_document = SimpleNamespace(
        id=uuid.uuid4(),
        crawl_run_id=uuid.uuid4(),
        merchant_id=merchant_id,
        url=offer.product_url,
        doc_type="html",
        http_status=200,
        payload_sha256="d" * 64,
        payload_path="/app/apps/crawler/raw_documents/run/d.html",
        content_length=23456,
        stored_at=last_seen_at,
    )

    serialized = _serialize_offer_audit(
        [(offer, product, merchant, source_document)],
        price_context={
            str(product_id): [
                (str(offer.id), 399.95),
                (str(uuid.uuid4()), 499.95),
            ]
        },
    )

    assert serialized[0].price_warning == "large_gap_between_merchants"


def test_price_warning_flags_missing_source_document_after_price_checks():
    product_id = uuid.uuid4()
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        product_id=product_id,
        price_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
    )

    assert _price_warning(
        offer=offer,
        source_document=None,
        price_context={},
    ) == "missing_source_document"


def test_offer_audit_csv_includes_source_document_and_sanitizes_cells():
    offer = SimpleNamespace(
        offer_id=str(uuid.uuid4()),
        product_id=str(uuid.uuid4()),
        canonical_key="mpn:lenovo:83GW007KFR",
        title="=Lenovo V15 G5 IRL",
        brand="lenovo",
        merchant_id=str(uuid.uuid4()),
        merchant_slug="ldlc",
        merchant_name="LDLC",
        price_amount=499.95,
        shipping_amount=0.0,
        total_amount=499.95,
        availability="in_stock",
        product_url="https://www.ldlc.com/fiche/PB00728588.html",
        last_seen_at="2026-05-26T10:00:00+00:00",
        source_age_hours=1.25,
        is_stale=False,
        price_warning="ok",
        source_document=SimpleNamespace(
            raw_document_id=str(uuid.uuid4()),
            crawl_run_id=str(uuid.uuid4()),
            merchant_id=str(uuid.uuid4()),
            merchant_slug="ldlc",
            merchant_name="LDLC",
            url="https://www.ldlc.com/fiche/PB00728588.html",
            doc_type="html",
            http_status=200,
            payload_sha256="c" * 64,
            payload_path="/app/apps/crawler/raw_documents/run/c.html",
            content_length=34567,
            stored_at="2026-05-26T10:00:01+00:00",
        ),
    )

    content = _offer_audit_csv([offer])

    assert "offer_id,product_id,canonical_key,title,brand,merchant_slug" in content
    assert "is_stale,price_warning,raw_document_id" in content
    assert "'=Lenovo V15 G5 IRL" in content
    assert "499.95,0.00,499.95" in content
    assert "false,ok" in content
    assert "/app/apps/crawler/raw_documents/run/c.html" in content


def test_manual_output_path_supports_ldlc():
    crawl_run_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    assert _manual_output_path("ldlc", crawl_run_id) == (
        "/app/apps/crawler/scheduled/ldlc_manual_12345678.json"
    )


def test_request_queue_defaults_to_per_merchant_queue(monkeypatch):
    monkeypatch.delenv("CRAWLER_MATERIEL_REQUEST_QUEUE", raising=False)
    monkeypatch.setenv("CRAWLER_REQUEST_QUEUE", "crawler:run_requests")

    assert _request_queue("materiel") == "crawler:run_requests:materiel"


def test_request_queue_uses_merchant_override(monkeypatch):
    monkeypatch.setenv("CRAWLER_LDLC_REQUEST_QUEUE", "crawler:ldlc")

    assert _request_queue("ldlc") == "crawler:ldlc"


def test_require_ops_admin_token_rejects_unconfigured_token(monkeypatch):
    monkeypatch.delenv("OPS_ADMIN_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        require_ops_admin_token("secret")

    assert exc.value.status_code == 503


def test_require_ops_admin_token_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("OPS_ADMIN_TOKEN", "secret")

    with pytest.raises(HTTPException) as exc:
        require_ops_admin_token(None)

    assert exc.value.status_code == 401


def test_require_ops_admin_token_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("OPS_ADMIN_TOKEN", "secret")

    with pytest.raises(HTTPException) as exc:
        require_ops_admin_token("wrong")

    assert exc.value.status_code == 403


def test_require_ops_admin_token_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("OPS_ADMIN_TOKEN", "secret")

    assert require_ops_admin_token("secret") is None


def test_ops_routes_include_admin_dependency():
    ops_routes = [
        route for route in app.router.routes if getattr(route, "path", "").startswith("/ops/")
    ]

    assert ops_routes
    assert any(
        getattr(route, "path", "") == "/ops/offers/{offer_id}/source-document"
        for route in ops_routes
    )
    assert any(
        getattr(route, "path", "") == "/ops/offers/stale" for route in ops_routes
    )
    assert any(
        getattr(route, "path", "") == "/ops/offers/audit" for route in ops_routes
    )
    assert any(
        getattr(route, "path", "") == "/ops/offers/audit.csv" for route in ops_routes
    )
    route_paths = [getattr(route, "path", "") for route in app.router.routes]
    assert route_paths.index("/ops/offers/stale") < route_paths.index(
        "/ops/offers/{offer_id}/source-document"
    )
    assert route_paths.index("/ops/offers/audit") < route_paths.index(
        "/ops/offers/{offer_id}/source-document"
    )
    assert route_paths.index("/ops/offers/audit.csv") < route_paths.index(
        "/ops/offers/{offer_id}/source-document"
    )
    for route in ops_routes:
        dependencies = [dependency.call for dependency in route.dependant.dependencies]
        assert require_ops_admin_token in dependencies
