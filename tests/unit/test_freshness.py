from datetime import UTC, datetime

from apps.api.src.services.freshness import as_utc, is_stale, source_age_hours
from apps.api.src.services.repository import _source_seen_at
from apps.api.src.routers.search import _latest_seen_at


def test_source_age_uses_utc_datetimes():
    now = datetime(2026, 5, 26, 12, tzinfo=UTC)
    seen_at = datetime(2026, 5, 26, 6, tzinfo=UTC)

    assert source_age_hours(seen_at, now) == 6.0


def test_is_stale_uses_configurable_threshold(monkeypatch):
    monkeypatch.setenv("OFFER_STALE_AFTER_HOURS", "24")
    now = datetime(2026, 5, 26, 12, tzinfo=UTC)

    assert is_stale(datetime(2026, 5, 25, 13, tzinfo=UTC), now) is False
    assert is_stale(datetime(2026, 5, 25, 11, tzinfo=UTC), now) is True


def test_source_seen_at_normalizes_naive_crawl_dates():
    seen_at = _source_seen_at(datetime(2026, 5, 24, 4, 58, 33))

    assert seen_at == datetime(2026, 5, 24, 4, 58, 33, tzinfo=UTC)
    assert as_utc("2026-05-24T04:58:33") == seen_at


def test_search_latest_seen_at_uses_newest_offer_source():
    latest = _latest_seen_at(
        [
            {"last_seen_at": "2026-05-24T04:58:33+00:00"},
            {"last_seen_at": "2026-05-26T02:59:00+00:00"},
        ]
    )

    assert latest == datetime(2026, 5, 26, 2, 59, tzinfo=UTC)
