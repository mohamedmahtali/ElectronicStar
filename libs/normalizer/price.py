import re
from decimal import Decimal, InvalidOperation

_CLEAN = re.compile(r"[^\d,.]")

# Taux de change indicatifs vers EUR (à remplacer par un service live en prod)
_FX_TO_EUR: dict[str, Decimal] = {
    "EUR": Decimal("1"),
    "USD": Decimal("0.92"),
    "GBP": Decimal("1.17"),
    "CHF": Decimal("1.05"),
}


def normalize_price(raw: str, currency: str = "EUR") -> tuple[Decimal, str] | None:
    """Retourne (montant_eur, 'EUR') ou None si non parsable."""
    cleaned = _CLEAN.sub("", raw).replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    rate = _FX_TO_EUR.get(currency.upper(), Decimal("1"))
    return (amount * rate).quantize(Decimal("0.01")), "EUR"
