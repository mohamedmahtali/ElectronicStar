import importlib.util
from importlib.machinery import ModuleSpec
import sys
import types
from decimal import Decimal

if importlib.util.find_spec("scrapy") is None:
    scrapy_stub = types.ModuleType("scrapy")
    scrapy_stub.__spec__ = ModuleSpec("scrapy", loader=None)
    scrapy_stub.Spider = object
    scrapy_stub.Request = object
    sys.modules["scrapy"] = scrapy_stub

if importlib.util.find_spec("pydantic") is None:
    schemas_stub = types.ModuleType("libs.crawling.schemas")
    schemas_stub.__spec__ = ModuleSpec("libs.crawling.schemas", loader=None)
    schemas_stub.RawItem = object
    schemas_stub.ParsedOffer = object
    sys.modules["libs.crawling.schemas"] = schemas_stub

from apps.crawler.src.spiders.ldlc import (
    _dedupe_urls,
    _find_product_ld,
    _first_price_text,
    _parse_price,
    _price_from_offers,
)


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
