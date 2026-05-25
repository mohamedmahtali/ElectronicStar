import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from apps.api.src.routers.ops import _manual_output_path, _serialize_crawl_runs


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
