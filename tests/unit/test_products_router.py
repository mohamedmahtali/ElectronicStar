import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from apps.api.src.routers.products import _serialize_price_history


def test_serialize_price_history_includes_merchant_and_total():
    offer_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    history = SimpleNamespace(
        captured_at=datetime(2026, 5, 24, 15, 30, tzinfo=UTC),
        price_amount=Decimal("479.95"),
        shipping_amount=Decimal("4.99"),
        availability="in_stock",
    )
    offer = SimpleNamespace(id=offer_id)
    merchant = SimpleNamespace(
        id=merchant_id,
        slug="ldlc",
        display_name="LDLC",
    )

    points = _serialize_price_history([(history, offer, merchant)])

    assert len(points) == 1
    assert points[0].offer_id == str(offer_id)
    assert points[0].merchant_id == str(merchant_id)
    assert points[0].merchant_slug == "ldlc"
    assert points[0].merchant_name == "LDLC"
    assert points[0].price_amount == 479.95
    assert points[0].shipping_amount == 4.99
    assert points[0].total_amount == 484.94
    assert points[0].captured_at == "2026-05-24T15:30:00+00:00"
