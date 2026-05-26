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

from apps.crawler.src.spiders.ldlc import _parse_price  # noqa: E402
from apps.crawler.src.spiders.materiel import (  # noqa: E402
    MaterielSpider,
    _brand_from_title,
    _first_product_price_text,
    _sku_from_url,
    _value_after_label,
)

FIXTURES_DIR = Path("tests/fixtures/spiders")


def _html_response(filename: str, url: str):
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required for HTML spider fixture tests")
    scrapy_http = pytest.importorskip("scrapy.http")
    body = (FIXTURES_DIR / filename).read_bytes()
    request = scrapy_http.Request(url=url)
    return scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")


def test_sku_from_materiel_product_url():
    assert _sku_from_url("https://www.materiel.net/produit/202511270118.html") == "202511270118"


def test_first_product_price_skips_lowest_30_day_and_destockage_prices():
    price_text = _first_product_price_text(
        [
            "7% de remise avec le code BREAK jusqu'au 21/05",
            "743€",
            "95",
            "Prix le + bas sur 30j",
            "799€",
            "95",
            "dont éco-participation 3€98",
            "À partir de 719€95 dans la Zone destockage",
        ]
    )

    assert _parse_price(price_text) == Decimal("799.95")


def test_first_product_price_accepts_simple_product_price():
    assert _parse_price(_first_product_price_text(["Être informé d'une baisse de prix", "45€90"])) == Decimal("45.90")


def test_value_after_label_extracts_specs_value():
    texts = ["Informations générales", "Marque", "ALTYK", "Modèle", "L16F-I3P16-N05-2"]

    assert _value_after_label(texts, "Marque") == "ALTYK"
    assert _value_after_label(texts, "Modèle") == "L16F-I3P16-N05-2"


def test_brand_from_title_uses_first_word_fallback():
    assert _brand_from_title("Audio-Technica ATH-M50x Noir") == "Audio-Technica"


def test_materiel_spider_parses_lenovo_product_price_fixture():
    response = _html_response(
        "materiel_lenovo_product.html",
        "https://www.materiel.net/produit/202602240108.html",
    )

    item = MaterielSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "materiel"
    assert item.merchant_sku == "202602240108"
    assert item.source_title == "Lenovo V15 G5 IRL (83GW007KFR)"
    assert item.brand_raw == "Lenovo"
    assert item.price_amount == Decimal("499.95")
    assert item.availability == "in_stock"
    assert item.gtin == "0199271991237"
    assert item.mpn == "83GW007KFR"


def test_materiel_spider_parses_xiaomi_low_price_fixture():
    response = _html_response(
        "materiel_xiaomi_product.html",
        "https://www.materiel.net/produit/202410170035.html",
    )

    item = MaterielSpider()._from_css(response)

    assert item is not None
    assert item.merchant_sku == "202410170035"
    assert item.source_title == "Xiaomi Redmi Buds 6 Play Noir"
    assert item.brand_raw == "Xiaomi"
    assert item.price_amount == Decimal("12.95")
    assert item.availability == "in_stock"
    assert item.mpn == "BHR8776GL"
