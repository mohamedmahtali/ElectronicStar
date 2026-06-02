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

from apps.crawler.src.spiders.fnac import FnacSpider, _sku_from_url  # noqa: E402

FIXTURES_DIR = Path("tests/fixtures/spiders")


def _html_response(filename: str, url: str):
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required for HTML spider fixture tests")
    scrapy_http = pytest.importorskip("scrapy.http")
    body = (FIXTURES_DIR / filename).read_bytes()
    request = scrapy_http.Request(url=url)
    return scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")


# --- SKU extraction ---

def test_sku_from_url_standard():
    assert _sku_from_url("https://www.fnac.com/a16428375/Apple-MacBook-Air") == "16428375"


def test_sku_from_url_with_anchor():
    assert _sku_from_url("https://www.fnac.com/a16428375/Product#omnsearchpos=1") == "16428375"


def test_sku_from_url_no_match():
    assert _sku_from_url("https://www.fnac.com/Ordinateurs/n-10601/w-4") is None


def test_sku_requires_six_digits():
    assert _sku_from_url("https://www.fnac.com/a123/short") is None


# --- JSON-LD parsing ---

def test_fnac_spider_parses_macbook_json_ld():
    response = _html_response(
        "fnac_macbook_jsonld.html",
        "https://www.fnac.com/a16428375/Apple-MacBook-Air-13-M3",
    )

    item = FnacSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "fnac"
    assert item.merchant_sku == "16428375"
    assert item.source_title == 'Apple MacBook Air 13" M3 (MRXN3FN/A)'
    assert item.brand_raw == "Apple"
    assert item.price_amount == Decimal("1299.00")
    assert item.availability == "in_stock"
    assert item.gtin == "0194253879343"
    assert item.mpn == "MRXN3FN/A"


# --- CSS fallback ---

def test_fnac_spider_css_fallback_samsung():
    response = _html_response(
        "fnac_samsung_css.html",
        "https://www.fnac.com/a18500001/Samsung-Galaxy-S24",
    )

    item = FnacSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "fnac"
    assert item.merchant_sku == "18500001"
    assert item.source_title == "Samsung Galaxy S24 128Go Noir"
    assert item.brand_raw == "Samsung"
    assert item.availability == "in_stock"
    assert item.gtin == "8806095071794"


def test_fnac_spider_css_fallback_price_extracted():
    response = _html_response(
        "fnac_samsung_css.html",
        "https://www.fnac.com/a18500001/Samsung-Galaxy-S24",
    )

    item = FnacSpider()._from_css(response)

    assert item is not None
    assert item.price_amount == Decimal("759.99")


# --- Product link extraction ---

def test_fnac_spider_extracts_product_links():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    html = b"""
    <html><body>
      <a href="/a16428375/Apple-MacBook">MacBook</a>
      <a href="/a12345678/Samsung-TV">Samsung TV</a>
      <a href="/Ordinateurs/n-10601">Categorie</a>
      <a href="/a999/short-id">Too short</a>
    </body></html>
    """
    request = scrapy_http.Request(url="https://www.fnac.com/Ordinateurs/n-10601/w-4")
    response = scrapy_http.HtmlResponse(
        url="https://www.fnac.com/Ordinateurs/n-10601/w-4",
        request=request,
        body=html,
        encoding="utf-8",
    )

    links = FnacSpider().extract_product_links(response)

    assert "https://www.fnac.com/a16428375/Apple-MacBook" in links
    assert "https://www.fnac.com/a12345678/Samsung-TV" in links
    assert not any("n-10601" in link for link in links)
    assert not any("/a999/" in link for link in links)
