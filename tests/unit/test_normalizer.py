from decimal import Decimal

from libs.normalizer import normalize_brand, normalize_category, normalize_title
from libs.normalizer.price import normalize_price


def test_normalize_title_strips_accents():
    assert normalize_title("Télévision OLED 65\"") == 'television oled 65"'


def test_normalize_title_removes_noise():
    result = normalize_title("Samsung TV 65 OLED - Livraison gratuite")
    assert "livraison" not in result
    assert "samsung" in result


def test_normalize_brand_alias():
    assert normalize_brand("Hewlett Packard") == "hp"
    assert normalize_brand("SAMSUNG Electronics") == "samsung"


def test_normalize_brand_none():
    assert normalize_brand(None) is None
    assert normalize_brand("") is None


def test_normalize_price_eur():
    result = normalize_price("1 299,99 €")
    assert result is not None
    amount, currency = result
    assert amount == Decimal("1299.99")
    assert currency == "EUR"


def test_normalize_price_usd():
    result = normalize_price("999.00", "USD")
    assert result is not None
    amount, currency = result
    assert currency == "EUR"
    assert amount < Decimal("999")


def test_normalize_price_invalid():
    assert normalize_price("N/A") is None


def test_normalize_category_tv():
    assert normalize_category("Téléviseurs OLED Samsung") == "Électronique/TV & Audio/Téléviseurs"


def test_normalize_category_unknown():
    assert normalize_category("Accessoires divers") is None
