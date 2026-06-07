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

from apps.crawler.src.spiders.ldlc import _parse_price
from apps.crawler.src.spiders.materiel import (
    _brand_from_title,
    _first_product_price_text,
    _sku_from_url,
    _value_after_label,
)


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
