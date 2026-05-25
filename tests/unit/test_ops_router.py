import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api.main import app
from apps.api.src.routers.ops import (
    _manual_output_path,
    _request_queue,
    _serialize_crawl_runs,
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
    for route in ops_routes:
        dependencies = [dependency.call for dependency in route.dependant.dependencies]
        assert require_ops_admin_token in dependencies
