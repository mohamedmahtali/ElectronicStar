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

from apps.crawler.src.spiders.cybertek import CybertekSpider, _sku_from_url  # noqa: E402

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
        "https://www.cybertek.fr/pc-portable/asus-vivobook-v3607vj-160744.aspx"
    ) == "160744"


def test_sku_from_url_with_long_slug():
    assert _sku_from_url(
        "https://www.cybertek.fr/pc-portable/hp-omen-16-fhd-144hz-ryzen-ai-7-350-rtx-5070-32go-1to-w11-163252.aspx"
    ) == "163252"


def test_sku_from_url_no_match():
    assert _sku_from_url("https://www.cybertek.fr/pc-portable-40.aspx") is None


def test_sku_requires_five_digits():
    assert _sku_from_url("https://www.cybertek.fr/produit-9999.aspx") is None


# --- JSON-LD parsing ---

def test_cybertek_parses_asus_json_ld():
    response = _html_response(
        "cybertek_product_jsonld.html",
        "https://www.cybertek.fr/pc-portable/asus-vivobook-v3607vj-iscrp177-16-fhd-144hz-c5-210h-rtx-3050-16go-512go-sans-os-160744.aspx",
    )

    item = CybertekSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "cybertek"
    assert item.merchant_sku == "160744"
    assert item.source_title == "Vivobook 16FHD+ 144Hz/C5 210H/3050/16G/512G/FD"
    assert item.brand_raw == "Asus"
    assert item.price_amount == Decimal("689.99")
    assert item.availability == "in_stock"
    assert item.gtin == "4711636323512"
    assert item.mpn == "90NB15V1-M00BH0"


# --- CSS fallback ---

def test_cybertek_css_fallback_hp():
    response = _html_response(
        "cybertek_css_fallback.html",
        "https://www.cybertek.fr/pc-portable/hp-pavilion-15-eh3049nf-15-6-fhd-ryzen-5-7530u-16go-512go-w11-158321.aspx",
    )

    item = CybertekSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "cybertek"
    assert item.merchant_sku == "158321"
    assert item.source_title == "HP Pavilion 15-eh3049nf 15,6\" FHD Ryzen 5 7530U 16Go 512Go W11"
    assert item.brand_raw == "HP"
    assert item.price_amount == Decimal("649.99")
    assert item.availability == "in_stock"
    assert item.gtin == "0197961855797"


# --- Product link extraction ---

def test_cybertek_extracts_product_links():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "cybertek_listing.html").read_bytes()
    url = "https://www.cybertek.fr/pc-portable-40.aspx"
    request = scrapy_http.Request(url=url)
    response = scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")

    links = CybertekSpider().extract_product_links(response)

    assert "https://www.cybertek.fr/pc-portable/asus-vivobook-v3607vj-iscrp177-16-fhd-144hz-c5-210h-rtx-3050-16go-512go-sans-os-160744.aspx" in links
    assert "https://www.cybertek.fr/pc-portable/hp-omen-16-fhd-144hz-ryzen-ai-7-350-rtx-5070-32go-1to-w11-163252.aspx" in links
    assert "https://www.cybertek.fr/pc-portable/lenovo-loq-essential-15irx11-15-6-fhd-144hz-i5-13450hx-rtx-5050-16go-512go-sans-os-157718.aspx" in links
    # Exclure les liens catégorie et les refs trop courtes
    assert not any("/pc-portable-40.aspx" in link and "produit" not in link for link in links)
    assert not any("-9999.aspx" in link for link in links)


def test_cybertek_extracts_next_page():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "cybertek_listing.html").read_bytes()
    url = "https://www.cybertek.fr/pc-portable-40.aspx"
    request = scrapy_http.Request(url=url)
    response = scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")

    next_page = CybertekSpider().extract_next_page(response)

    assert next_page == "https://www.cybertek.fr/pc-portable-40.aspx?page=2"
