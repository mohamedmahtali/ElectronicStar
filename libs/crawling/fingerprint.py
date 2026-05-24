import hashlib
import json


def compute_fingerprint(merchant_slug: str, merchant_sku: str, condition: str = "new") -> str:
    """Fingerprint stable de l'offre courante.

    Le prix et la disponibilité changent dans le temps : ils appartiennent à
    price_history, pas à l'identité de l'offre.
    """
    payload = json.dumps(
        {
            "merchant_slug": merchant_slug,
            "merchant_sku": merchant_sku,
            "condition": condition,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
