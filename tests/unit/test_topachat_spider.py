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

from apps.crawler.src.spiders.topachat import TopAchatSpider, _sku_from_url  # noqa: E402

FIXTURES_DIR = Path("tests/fixtures/spiders")


def _html_response(filename: str, url: str):
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy and pydantic are required for HTML spider fixture tests")
    scrapy_http = pytest.importorskip("scrapy.http")
    body = (FIXTURES_DIR / filename).read_bytes()
    request = scrapy_http.Request(url=url)
    return scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")


# --- SKU extraction ---

def test_sku_from_url_laptop():
    assert _sku_from_url(
        "https://www.topachat.com/pages/detail2_cat_est_ordinateurs_puis_rubrique_est_wport_puis_ref_est_in20031672.html"
    ) == "in20031672"


def test_sku_from_url_gpu():
    assert _sku_from_url(
        "https://www.topachat.com/pages/detail2_cat_est_micro_puis_rubrique_est_wgfx_pcie_puis_ref_est_in20031999.html"
    ) == "in20031999"


def test_sku_from_url_no_match_listing():
    assert _sku_from_url(
        "https://www.topachat.com/pages/produits_cat_est_ordinateurs_puis_rubrique_est_wport.html"
    ) is None


def test_sku_from_url_no_match_category():
    assert _sku_from_url(
        "https://www.topachat.com/pages/detail2_cat_est_ordinateurs.html"
    ) is None


# --- JSON-LD parsing (liste) ---

def test_topachat_parses_lenovo_json_ld():
    response = _html_response(
        "topachat_product_jsonld.html",
        "https://www.topachat.com/pages/detail2_cat_est_ordinateurs_puis_rubrique_est_wport_puis_ref_est_in20031672.html",
    )

    item = TopAchatSpider()._from_json_ld(response)

    assert item is not None
    assert item.merchant_slug == "topachat"
    assert item.merchant_sku == "in20031672"
    assert item.source_title == "Lenovo IdeaPad Slim 5 14IRH10 (83HR006FFR)"
    assert item.brand_raw == "LENOVO"
    assert item.price_amount == Decimal("729.99")
    assert item.availability == "in_stock"
    assert item.gtin == "198157068438"
    assert item.mpn == "83HR006FFR"


# --- CSS fallback ---

def test_topachat_css_fallback_msi():
    response = _html_response(
        "topachat_css_fallback.html",
        "https://www.topachat.com/pages/detail2_cat_est_micro_puis_rubrique_est_wgfx_pcie_puis_ref_est_in20031999.html",
    )

    item = TopAchatSpider()._from_css(response)

    assert item is not None
    assert item.merchant_slug == "topachat"
    assert item.merchant_sku == "in20031999"
    assert item.source_title == "MSI GeForce RTX 5070 Ti 16G GAMING TRIO"
    assert item.brand_raw == "MSI"
    assert item.price_amount == Decimal("899.99")
    assert item.availability == "in_stock"
    assert item.gtin == "4719072215385"


# --- Product link extraction ---

def test_topachat_extracts_product_links():
    if not HAS_SCRAPY or not HAS_PYDANTIC:
        pytest.skip("Scrapy required")
    scrapy_http = pytest.importorskip("scrapy.http")

    body = (FIXTURES_DIR / "topachat_listing.html").read_bytes()
    url = "https://www.topachat.com/pages/produits_cat_est_ordinateurs_puis_rubrique_est_wport.html"
    request = scrapy_http.Request(url=url)
    response = scrapy_http.HtmlResponse(url=url, request=request, body=body, encoding="utf-8")

    links = TopAchatSpider().extract_product_links(response)

    assert "https://www.topachat.com/pages/detail2_cat_est_ordinateurs_puis_rubrique_est_wport_puis_ref_est_in20031672.html" in links
    assert "https://www.topachat.com/pages/detail2_cat_est_ordinateurs_puis_rubrique_est_wport_puis_ref_est_in20031780.html" in links
    assert "https://www.topachat.com/pages/detail2_cat_est_ordinateurs_puis_rubrique_est_wport_puis_ref_est_in20031845.html" in links
    assert not any("produits_cat_est" in link for link in links)
    assert not any("detail2_cat_est_ordinateurs.html" in link for link in links)
