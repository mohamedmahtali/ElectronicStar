import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from libs.crawling.schemas import ParsedOffer
from libs.matcher.engine import MatchEngine, MatchStrategy


def _make_offer(**kwargs) -> ParsedOffer:
    defaults = dict(
        merchant_slug="shop_a",
        merchant_sku="SKU-001",
        product_url="https://shop.example.com/p/001",
        title_norm="samsung tv oled 65",
        brand_norm="samsung",
        price_amount=Decimal("999.99"),
        fingerprint="abc123",
    )
    defaults.update(kwargs)
    return ParsedOffer(**defaults)


@pytest.mark.asyncio
async def test_match_by_gtin():
    product_id = uuid.uuid4()
    db = AsyncMock()
    db.find_by_gtin.return_value = product_id

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin="3614273899215"))

    assert result.product_id == product_id
    assert result.strategy == MatchStrategy.GTIN
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_match_by_mpn_brand():
    product_id = uuid.uuid4()
    db = AsyncMock()
    db.find_by_gtin.return_value = None
    db.find_by_mpn_brand.return_value = product_id

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin=None, mpn="QE65S95D", brand_norm="samsung"))

    assert result.product_id == product_id
    assert result.strategy == MatchStrategy.MPN_BRAND


@pytest.mark.asyncio
async def test_match_creates_new_product_when_no_candidate():
    db = AsyncMock()
    db.find_by_gtin.return_value = None
    db.find_by_mpn_brand.return_value = None
    db.find_by_known_sku.return_value = None
    db.find_by_trigram.return_value = []
    db.enqueue_review.return_value = None

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin=None, mpn=None))

    assert result.product_id is None
    assert result.strategy == MatchStrategy.NEW_PRODUCT
    assert result.needs_review is False
    db.enqueue_review.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_creates_new_product_for_unknown_gtin_without_trigram_review():
    db = AsyncMock()
    db.find_by_gtin.return_value = None
    db.find_by_mpn_brand.return_value = None
    db.find_by_known_sku.return_value = None
    db.find_by_trigram.return_value = [(uuid.uuid4(), 0.72)]
    db.enqueue_review.return_value = None

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin="0745883929702", mpn=None))

    assert result.product_id is None
    assert result.strategy == MatchStrategy.NEW_PRODUCT
    assert result.needs_review is False
    db.find_by_trigram.assert_not_awaited()
    db.enqueue_review.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_known_sku_still_wins_for_unknown_gtin():
    product_id = uuid.uuid4()
    db = AsyncMock()
    db.find_by_gtin.return_value = None
    db.find_by_mpn_brand.return_value = None
    db.find_by_known_sku.return_value = product_id

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin="0745883929702", mpn=None))

    assert result.product_id == product_id
    assert result.strategy == MatchStrategy.KNOWN_SKU


@pytest.mark.asyncio
async def test_match_trigram_high_confidence():
    product_id = uuid.uuid4()
    db = AsyncMock()
    db.find_by_gtin.return_value = None
    db.find_by_mpn_brand.return_value = None
    db.find_by_known_sku.return_value = None
    db.find_by_trigram.return_value = [(product_id, 0.92)]

    engine = MatchEngine(db)
    result = await engine.match(_make_offer(gtin=None, mpn=None))

    assert result.product_id == product_id
    assert result.strategy == MatchStrategy.TRIGRAM
    assert result.confidence == pytest.approx(0.92)
