import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from apps.api.src.routers.products import _offers_csv, _price_history_csv, _serialize_price_history


def test_serialize_price_history_includes_merchant_and_total():
    offer_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    history = SimpleNamespace(
        captured_at=datetime(2026, 5, 24, 15, 30, tzinfo=UTC),
        price_amount=Decimal("499.95"),
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
    assert points[0].price_amount == 499.95
    assert points[0].shipping_amount == 4.99
    assert points[0].total_amount == 504.94
    assert points[0].captured_at == "2026-05-24T15:30:00+00:00"


def test_offers_csv_includes_product_and_offer_rows():
    product_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    product = SimpleNamespace(
        id=product_id,
        canonical_key="gtin:0199271991237",
        title_display="Lenovo V15 G5 IRL",
        brand_norm="lenovo",
    )
    offer = SimpleNamespace(
        merchant_id=str(merchant_id),
        merchant_slug="ldlc",
        merchant_name="LDLC",
        seller_name=None,
        price_amount=499.95,
        shipping_amount=0.0,
        availability="in_stock",
        condition="new",
        product_url="https://www.ldlc.com/fiche/PB00728588.html",
        last_seen_at="2026-05-25T18:00:00+00:00",
    )

    content = _offers_csv(product, [offer])

    assert "product_id,canonical_key,title,brand,merchant_slug" in content
    assert str(product_id) in content
    assert "Lenovo V15 G5 IRL" in content
    assert "499.95,0.00,499.95" in content


def test_price_history_csv_includes_total_and_sanitizes_formula_cells():
    product = SimpleNamespace(
        id=uuid.uuid4(),
        canonical_key="mpn:test:=danger",
        title_display="=Formula title",
        brand_norm="test",
    )
    point = SimpleNamespace(
        offer_id=str(uuid.uuid4()),
        merchant_slug="materiel",
        merchant_name="Materiel.net",
        captured_at="2026-05-25T18:00:00+00:00",
        price_amount=12.95,
        shipping_amount=0.0,
        total_amount=12.95,
        availability="in_stock",
    )

    content = _price_history_csv(product, [point])

    assert "product_id,canonical_key,title,brand,offer_id" in content
    assert "'=Formula title" in content
    assert "12.95,0.00,12.95" in content
