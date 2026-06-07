import unicodedata

# Aliases de marques connus → forme canonique
_BRAND_ALIASES: dict[str, str] = {
    "samsung electronics": "samsung",
    "apple inc": "apple",
    "lg electronics": "lg",
    "hewlett packard": "hp",
    "hewlett-packard": "hp",
}


def normalize_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    nfkd = unicodedata.normalize("NFKD", raw)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
    return _BRAND_ALIASES.get(cleaned, cleaned) or None
