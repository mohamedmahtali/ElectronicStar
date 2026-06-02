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

from apps.crawler.src.spiders.grosbill import GrosbillSpider, _sku_from_url  # noqa: E402

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
    assert _sku_from_url(
        "https://www.grosbill.com/pc-portable/asus-vivobook-x1605va-iscsh2797w-16-oled-fhd-core-9-270h-16go-512go-w11-160838.aspx"
    ) == "160838"


def test_sku_from_url_gpu():
    assert _sku_from_url(
        "https://www.grosbill.com/carte-graphique/msi-geforce-rtx-5060-ti-8g-ventus-2x-oc-167902.aspx"
    ) == "167902"


def test_sku_from_url_no_match():
    assert _sku_from_url("https://www.grosbill.com/pc-portable-40.aspx") is None


def test_sku_requires_five_digits():
    assert _sku_from_url("https://www.grosbill.com/produit-9999.aspx") is None


# --- JSON-LD parsing ---

def test_grosbill_parses_asus_json_ld():
    response = _html_response(
        "grosbill_product_jsonld.html",
        "https://www.grosbill.com/pc-portable/asus-vivobook-x1605va-iscsh2797w-16-oled-fhd-core-9-270h-16go-512go-w11-160838.aspx",
    )

    item = GrosbillSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "grosbill"
    assert item.merchant_sku == "160838"
    assert item.source_title == "Vivobook 16OLED FHD+/Core 9 270H/16Go/512Go/W11"
    assert item.brand_raw == "Asus"
    assert item.price_amount == Decimal("999.90")
    assert item.availability == "in_stock"
    assert item.gtin == "4711636323765"
    assert item.mpn == "90NB13W3-M00TF0"


# --- CSS fallback ---

def test_grosbill_css_fallback_msi():
    response = _html_response(
        "grosbill_css_fallback.html",
        "https://www.grosbill.com/carte-graphique/msi-geforce-rtx-5060-ti-8g-ventus-2x-oc-167902.aspx",
    )

    item = GrosbillSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "grosbill"
    assert item.merchant_sku == "167902"
    assert item.source_title == "MSI GeForce RTX 5060 Ti 8G VENTUS 2X OC"
    assert item.brand_raw == "MSI"
    assert item.price_amount == Decimal("449.99")
    assert item.availability == "in_stock"
    assert item.gtin == "4719072207038"


# --- Product link extraction ---

def test_grosbill_extracts_product_links():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "grosbill_listing.html").read_bytes()
    url = "https://www.grosbill.com/pc-portable-40.aspx"
    request = scrapy_http.Request(url=url)
    response = scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")

    links = GrosbillSpider().extract_product_links(response)

    assert "https://www.grosbill.com/pc-portable/asus-vivobook-x1605va-iscsh2797w-16-oled-fhd-core-9-270h-16go-512go-w11-160838.aspx" in links
    assert "https://www.grosbill.com/pc-portable/gigabyte-gaming-a16-cthi3fr894sh-16-fhd-165hz-i7-13620h-rtx-5050-16go-1to-w11-150378.aspx" in links
    assert "https://www.grosbill.com/pc-portable/asus-gaming-v16-v3607vm-rp047w-16-fhd-core-5-210h-rtx-5060-16go-512go-w11-154249.aspx" in links
    assert not any("/pc-portable-40.aspx?crits=" in link for link in links)
    assert not any("-9999.aspx" in link for link in links)


def test_grosbill_extracts_next_page():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "grosbill_listing.html").read_bytes()
    url = "https://www.grosbill.com/pc-portable-40.aspx"
    request = scrapy_http.Request(url=url)
    response = scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")

    next_page = GrosbillSpider().extract_next_page(response)

    assert next_page == "https://www.grosbill.com/pc-portable-40.aspx?page=2"
