import importlib.util
from importlib.machinery import ModuleSpec
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest

HAS_SCRAPY = importlib.util.find_spec("scrapy") is not None
HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None

if not HAS_SCRAPY:
    scrapy_stub = types.ModuleType("scrapy")
    scrapy_stub.__spec__ = ModuleSpec("scrapy", loader=None)
    scrapy_stub.Spider = object
    scrapy_stub.Request = object
    sys.modules["scrapy"] = scrapy_stub

if not HAS_PYDANTIC:
    schemas_stub = types.ModuleType("libs.crawling.schemas")
    schemas_stub.__spec__ = ModuleSpec("libs.crawling.schemas", loader=None)
    schemas_stub.RawItem = object
    schemas_stub.ParsedOffer = object
    sys.modules["libs.crawling.schemas"] = schemas_stub

from apps.crawler.src.spiders.ldlc import (  # noqa: E402
    LdlcSpider,
    _dedupe_urls,
    _find_product_ld,
    _first_price_text,
    _parse_price,
    _price_from_offers,
)

FIXTURES_DIR = Path("tests/fixtures/spiders")


def _html_response(filename: str, url: str):
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required for HTML spider fixture tests")
    scrapy_http = pytest.importorskip("scrapy.http")
    body = (FIXTURES_DIR / filename).read_bytes()
    request = scrapy_http.Request(url=url)
    return scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")


def test_parse_ldlc_price_with_euro_as_separator():
    assert _parse_price("1 199€95") == Decimal("1199.95")
    assert _parse_price("999€00") == Decimal("999.00")


def test_parse_ldlc_price_with_decimal_separator():
    assert _parse_price("1 299,99 €") == Decimal("1299.99")
    assert _parse_price("1299.99") == Decimal("1299.99")


def test_price_from_offer_accepts_low_price():
    assert _price_from_offers({"lowPrice": "549.00"}) == Decimal("549.00")


def test_first_price_text_skips_monthly_financing():
    price_text = _first_price_text(
        ["A partir de", "44€", "53/mois", "ou", "1 329€", "00", "Éco-part."]
    )

    assert _parse_price(price_text) == Decimal("1329.00")


def test_find_product_ld_in_graph():
    data = {
        "@graph": [
            {"@type": "BreadcrumbList"},
            {"@type": ["Product"], "name": "Hisense 65U7NQ"},
        ]
    }

    assert _find_product_ld(data) == {"@type": ["Product"], "name": "Hisense 65U7NQ"}


def test_dedupe_urls_preserves_order():
    assert _dedupe_urls(["/fiche/PB1.html", "/fiche/PB2.html", "/fiche/PB1.html"]) == [
        "/fiche/PB1.html",
        "/fiche/PB2.html",
    ]


def test_ldlc_spider_parses_lenovo_json_ld_fixture():
    response = _html_response(
        "ldlc_lenovo_jsonld.html",
        "https://www.ldlc.com/fiche/PB00728588.html",
    )

    item = LdlcSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "ldlc"
    assert item.merchant_sku == "PB00728588"
    assert item.source_title == "Lenovo V15 G5 IRL (83GW007KFR)"
    assert item.brand_raw == "Lenovo"
    assert item.price_amount == Decimal("499.95")
    assert item.availability == "in_stock"
    assert item.gtin == "0199271991237"
    assert item.mpn == "83GW007KFR"


def test_ldlc_spider_css_fallback_keeps_product_price_over_financing():
    response = _html_response(
        "ldlc_lenovo_css.html",
        "https://www.ldlc.com/fiche/PB00728588.html",
    )

    item = LdlcSpider()._from_css(response)

    assert item is not None
    assert item.merchant_sku == "PB00728588"
    assert item.source_title == "Lenovo V15 G5 IRL (83GW007KFR)"
    assert item.brand_raw == "Lenovo"
    assert item.price_amount == Decimal("499.95")
    assert item.availability == "in_stock"
