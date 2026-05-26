import os
from datetime import UTC, datetime

DEFAULT_OFFER_STALE_AFTER_HOURS = 24.0


def as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def source_age_hours(value: datetime | str | None, now: datetime | None = None) -> float | None:
    seen_at = as_utc(value)
    if seen_at is None:
        return None
    current = as_utc(now) or datetime.now(UTC)
    return round(max((current - seen_at).total_seconds(), 0) / 3600, 3)


def is_stale(value: datetime | str | None, now: datetime | None = None) -> bool:
    age = source_age_hours(value, now)
    if age is None:
        return True
    return age > offer_stale_after_hours()


def offer_stale_after_hours() -> float:
    raw_value = os.getenv("OFFER_STALE_AFTER_HOURS", "").strip()
    if not raw_value:
        return DEFAULT_OFFER_STALE_AFTER_HOURS
    try:
        return max(float(raw_value), 0)
    except ValueError:
        return DEFAULT_OFFER_STALE_AFTER_HOURS
