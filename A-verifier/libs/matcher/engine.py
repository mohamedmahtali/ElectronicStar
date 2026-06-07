"""Matching canonique en 5 niveaux selon le plan :
1. GTIN/EAN/UPC strict
2. MPN + marque
3. SKU marchand déjà connu (product_aliases)
4. Similarité trigrammes sur brand_norm + title_norm (pg_trgm)
5. File de revue manuelle
"""
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from libs.crawling.schemas import ParsedOffer


class MatchStrategy(str, Enum):
    GTIN = "gtin"
    MPN_BRAND = "mpn_brand"
    KNOWN_SKU = "known_sku"
    TRIGRAM = "trigram"
    NEW_PRODUCT = "new_product"
    REVIEW_QUEUE = "review_queue"


@dataclass
class MatchResult:
    product_id: uuid.UUID | None
    strategy: MatchStrategy
    confidence: float  # 0.0–1.0
    needs_review: bool = False


class DBPort(Protocol):
    """Interface vers la base — implémentée côté apps/api."""

    async def find_by_gtin(self, gtin: str) -> uuid.UUID | None: ...
    async def find_by_mpn_brand(self, mpn: str, brand_norm: str) -> uuid.UUID | None: ...
    async def find_by_known_sku(self, merchant_slug: str, merchant_sku: str) -> uuid.UUID | None: ...
    async def find_by_trigram(self, brand_norm: str, title_norm: str, category_path: str | None) -> list[tuple[uuid.UUID, float]]: ...
    async def enqueue_review(self, offer: ParsedOffer, candidates: list[tuple[uuid.UUID, float]]) -> None: ...


class MatchEngine:
    TRIGRAM_HIGH_THRESHOLD = 0.85
    TRIGRAM_LOW_THRESHOLD = 0.60

    def __init__(self, db: DBPort) -> None:
        self._db = db

    async def match(self, offer: ParsedOffer) -> MatchResult:
        # 1. GTIN strict
        if offer.gtin:
            product_id = await self._db.find_by_gtin(offer.gtin)
            if product_id:
                return MatchResult(product_id=product_id, strategy=MatchStrategy.GTIN, confidence=1.0)

        # 2. MPN + marque
        if offer.mpn and offer.brand_norm:
            product_id = await self._db.find_by_mpn_brand(offer.mpn, offer.brand_norm)
            if product_id:
                return MatchResult(product_id=product_id, strategy=MatchStrategy.MPN_BRAND, confidence=0.97)

        # 3. SKU marchand déjà connu
        product_id = await self._db.find_by_known_sku(offer.merchant_slug, offer.merchant_sku)
        if product_id:
            return MatchResult(product_id=product_id, strategy=MatchStrategy.KNOWN_SKU, confidence=0.99)

        if offer.gtin or (offer.mpn and offer.brand_norm):
            return MatchResult(
                product_id=None,
                strategy=MatchStrategy.NEW_PRODUCT,
                confidence=1.0,
                needs_review=False,
            )

        # 4. Similarité trigrammes
        if offer.brand_norm and offer.title_norm:
            candidates = await self._db.find_by_trigram(
                offer.brand_norm, offer.title_norm, offer.category_path
            )
            if candidates:
                best_id, best_score = candidates[0]
                if best_score >= self.TRIGRAM_HIGH_THRESHOLD:
                    return MatchResult(
                        product_id=best_id, strategy=MatchStrategy.TRIGRAM, confidence=best_score
                    )
                if best_score >= self.TRIGRAM_LOW_THRESHOLD:
                    await self._db.enqueue_review(offer, candidates)
                    return MatchResult(
                        product_id=None, strategy=MatchStrategy.REVIEW_QUEUE,
                        confidence=best_score, needs_review=True
                    )

        # 5. Aucun candidat : c'est un nouveau produit canonique.
        return MatchResult(
            product_id=None,
            strategy=MatchStrategy.NEW_PRODUCT,
            confidence=1.0,
            needs_review=False,
        )
