import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(path: str) -> list[dict]:
    payload = json.loads((ROOT / path).read_text())
    assert isinstance(payload, list)
    return payload


def _find_lenovo(rows: list[dict]) -> dict:
    return next(row for row in rows if row.get("gtin") == "0199271991237")


def test_default_demo_fixtures_keep_lenovo_prices_realistic():
    ldlc = _find_lenovo(_load("tests/fixtures/ingest/ldlc.json"))
    materiel = _find_lenovo(_load("tests/fixtures/ingest/materiel.json"))
    repeated_ldlc = _find_lenovo(_load("tests/fixtures/ingest/ldlc_price_change.json"))

    assert ldlc["price_amount"] == "499.95"
    assert materiel["price_amount"] == "499.95"
    assert repeated_ldlc["price_amount"] == "499.95"


def test_price_drop_fixture_is_isolated():
    drop = _find_lenovo(_load("tests/fixtures/price_drop/ldlc_price_drop.json"))

    assert drop["merchant_slug"] == "ldlc"
    assert drop["price_amount"] == "479.95"


def test_makefile_exposes_dedicated_price_drop_demo():
    makefile = (ROOT / "Makefile").read_text()

    assert "demo-price-drop:" in makefile
    assert "tests/fixtures/price_drop/ldlc_price_drop.json" in makefile
