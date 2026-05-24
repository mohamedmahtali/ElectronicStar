import re
import unicodedata

_NOISE = re.compile(
    r"\b(neuf|new|occasion|reconditionné|reconditionne|livraison gratuite|"
    r"free shipping|promo|soldes?|offre|prix\s+\w+|stock\s+\w+)\b",
    re.IGNORECASE,
)
_MULTI_SPACE = re.compile(r"\s{2,}")


def normalize_title(raw: str) -> str:
    """Normalise un titre produit pour le matching : bas de casse, sans accents, sans bruit marchand."""
    if not raw:
        return ""
    # Décomposition Unicode → suppression diacritiques
    nfkd = unicodedata.normalize("NFKD", raw)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = ascii_str.lower()
    # Suppression du bruit commercial
    cleaned = _NOISE.sub(" ", lower)
    # Normalisation des espaces
    return _MULTI_SPACE.sub(" ", cleaned).strip()
