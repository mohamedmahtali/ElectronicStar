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
    sys.modules["libs.crawling.schemas"] = schemas_stub

from apps.crawler.src.spiders.boulanger import BoulangerSpider, _ref_from_url  # noqa: E402

FIXTURES_DIR = Path("tests/fixtures/spiders")


def _html_response(filename: str, url: str):
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required for HTML spider fixture tests")
    scrapy_http = pytest.importorskip("scrapy.http")
    body = (FIXTURES_DIR / filename).read_bytes()
    request = scrapy_http.Request(url=url)
    return scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")


# --- SKU/ref extraction ---

def test_ref_from_url_standard():
    assert _ref_from_url("https://www.boulanger.com/ref/1222397") == "1222397"


def test_ref_from_url_with_slug():
    assert _ref_from_url("https://www.boulanger.com/ref/1222397/hp-14-em0042nf") == "1222397"


def test_ref_from_url_no_match():
    assert _ref_from_url("https://www.boulanger.com/c/tous-les-ordinateurs-portables") is None


def test_ref_requires_five_digits():
    assert _ref_from_url("https://www.boulanger.com/ref/9999") is None


# --- JSON-LD parsing ---

def test_boulanger_parses_hp_json_ld():
    response = _html_response(
        "boulanger_hp_jsonld.html",
        "https://www.boulanger.com/ref/1222397",
    )

    item = BoulangerSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "boulanger"
    assert item.merchant_sku == "1222397"
    assert item.source_title == "Ordinateur portable HP 14-em0042nf"
    assert item.brand_raw == "HP"
    assert item.price_amount == Decimal("499.99")
    assert item.availability == "in_stock"
    assert item.gtin == "0199251199059"


def test_boulanger_parses_price_with_single_decimal():
    """Boulanger JSON-LD peut envoyer '1519.0' (un seul chiffre décimal)."""
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required")
    scrapy_http = pytest.importorskip("scrapy.http")
    html = b"""<!doctype html><html><head>
    <script type="application/ld+json">
    {"@context":"http://schema.org","@type":"Product","name":"Smartphone SAMSUNG Galaxy S26",
     "sku":"uuid-123","gtin13":null,
     "brand":{"@type":"Brand","name":"SAMSUNG"},
     "offers":{"@type":"Offer","price":"1519.0","priceCurrency":"EUR",
               "availability":"https://schema.org/InStock"}}
    </script></head><body><h1>Smartphone SAMSUNG Galaxy S26</h1></body></html>"""
    request = scrapy_http.Request(url="https://www.boulanger.com/ref/1235776")
    response = scrapy_http.HtmlResponse(
        url="https://www.boulanger.com/ref/1235776", request=request,
        body=html, encoding="utf-8",
    )

    item = BoulangerSpider()._from_json_ld(response)

    assert item is not None
    assert item.price_amount == Decimal("1519.0")
    assert item.source_title == "Smartphone SAMSUNG Galaxy S26"


# --- CSS fallback ---

def test_boulanger_css_fallback_samsung():
    response = _html_response(
        "boulanger_css_fallback.html",
        "https://www.boulanger.com/ref/18500001",
    )

    item = BoulangerSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "boulanger"
    assert item.merchant_sku == "18500001"
    assert item.source_title == "Samsung Galaxy S24 128Go Noir"
    assert item.brand_raw == "Samsung"
    assert item.price_amount == Decimal("759.99")
    assert item.availability == "in_stock"
    assert item.gtin == "8806095071794"


# --- Product link extraction ---

def test_boulanger_extracts_product_links():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "boulanger_listing.html").read_bytes()
    request = scrapy_http.Request(url="https://www.boulanger.com/c/tous-les-ordinateurs-portables")
    response = scrapy_http.HtmlResponse(
        url="https://www.boulanger.com/c/tous-les-ordinateurs-portables",
        request=request,
        body=body,
        encoding="utf-8",
    )

    links = BoulangerSpider().extract_product_links(response)

    assert "https://www.boulanger.com/ref/1222397" in links
    assert "https://www.boulanger.com/ref/1219080" in links
    assert "https://www.boulanger.com/ref/1236129" in links
    assert not any("/c/" in link for link in links)
    assert not any("/ref/99" in link for link in links)


def test_boulanger_extracts_next_page():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "boulanger_listing.html").read_bytes()
    request = scrapy_http.Request(url="https://www.boulanger.com/c/tous-les-ordinateurs-portables")
    response = scrapy_http.HtmlResponse(
        url="https://www.boulanger.com/c/tous-les-ordinateurs-portables",
        request=request,
        body=body,
        encoding="utf-8",
    )

    next_page = BoulangerSpider().extract_next_page(response)

    assert next_page == "https://www.boulanger.com/c/tous-les-ordinateurs-portables?numPage=2"
