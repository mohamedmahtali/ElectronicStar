from statistics import median
from typing import Protocol

PRICE_GAP_WARNING_RATIO = 0.15
PRICE_WARNING_OK = "ok"
PRICE_WARNING_LARGE_GAP = "large_gap_between_merchants"
PRICE_WARNING_MISSING_SOURCE = "missing_source_document"
PRICE_QUARANTINED_WARNINGS = {PRICE_WARNING_LARGE_GAP}


class PricedOffer(Protocol):
    id: object
    product_id: object
    price_amount: object
    shipping_amount: object


def build_price_context(offers: list[PricedOffer]) -> dict[str, list[tuple[str, float]]]:
    context: dict[str, list[tuple[str, float]]] = {}
    for offer in offers:
        context.setdefault(str(offer.product_id), []).append(
            (str(offer.id), offer_total_amount(offer))
        )
    return context


def offer_total_amount(offer: PricedOffer) -> float:
    return float(offer.price_amount) + float(offer.shipping_amount)


def price_warning_for_offer(
    offer: PricedOffer,
    *,
    price_context: dict[str, list[tuple[str, float]]],
    has_source_document: bool = True,
) -> str:
    return price_warning_for_values(
        offer_id=str(offer.id),
        product_id=str(offer.product_id),
        total_amount=offer_total_amount(offer),
        price_context=price_context,
        has_source_document=has_source_document,
    )


def price_warning_for_values(
    *,
    offer_id: str,
    product_id: str,
    total_amount: float,
    price_context: dict[str, list[tuple[str, float]]],
    has_source_document: bool = True,
) -> str:
    peer_totals = [
        peer_total
        for peer_offer_id, peer_total in price_context.get(product_id, [])
        if peer_offer_id != offer_id
    ]
    peer_median = median(peer_totals) if peer_totals else None
    if peer_median and peer_median > 0:
        gap_ratio = (peer_median - total_amount) / peer_median
        if gap_ratio > PRICE_GAP_WARNING_RATIO:
            return PRICE_WARNING_LARGE_GAP

    if not has_source_document:
        return PRICE_WARNING_MISSING_SOURCE

    return PRICE_WARNING_OK


def is_price_quarantined(price_warning: str | None) -> bool:
    return price_warning in PRICE_QUARANTINED_WARNINGS
