"""Indexeur Elasticsearch : construit le document produit dénormalisé et le bulk-indexe."""
import logging
import uuid
from datetime import UTC, datetime

from elasticsearch import AsyncElasticsearch
from sqlalchemy import select

from apps.api.src.db.models import Offer, Product
from apps.api.src.search.es_mappings import PRODUCTS_INDEX_WRITE

logger = logging.getLogger(__name__)


class ESIndexer:
    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es

    async def index_product(self, product_id: uuid.UUID, repo) -> None:
        """Reconstruit et indexe le document produit complet depuis la DB."""
        from sqlalchemy import select as sa_select

        product_row = await repo._s.execute(
            sa_select(Product).where(Product.id == product_id)
        )
        product: Product | None = product_row.scalar_one_or_none()
        if not product:
            return

        offers_row = await repo._s.execute(
            sa_select(Offer).where(Offer.product_id == product_id)
        )
        offers: list[Offer] = offers_row.scalars().all()

        prices = [float(o.price_amount) for o in offers]
        doc = {
            "product_id": str(product.id),
            "canonical_key": product.canonical_key,
            "title": product.title_display,
            "brand": product.brand_norm,
            "category_path": product.category_path,
            "gtin": product.gtin,
            "mpn": product.mpn,
            "specs": product.specs,
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
            "merchant_ids": list({str(o.merchant_id) for o in offers}),
            "offers": [
                {
                    "merchant_id": str(o.merchant_id),
                    "merchant_name": None,
                    "price_amount": float(o.price_amount),
                    "shipping_amount": float(o.shipping_amount),
                    "availability": o.availability,
                    "condition": o.condition,
                    "product_url": o.product_url,
                    "last_seen_at": o.last_seen_at.isoformat() if o.last_seen_at else None,
                }
                for o in offers
            ],
            "updated_at": datetime.now(UTC).isoformat(),
        }

        await self._es.index(
            index=PRODUCTS_INDEX_WRITE,
            id=str(product_id),
            document=doc,
        )
        logger.debug("Indexed product %s into ES", product_id)

    async def bulk_index(self, docs: list[dict]) -> None:
        """Indexation bulk pour le reindex complet."""
        if not docs:
            return
        actions = []
        for doc in docs:
            actions.append({"index": {"_index": PRODUCTS_INDEX_WRITE, "_id": doc["product_id"]}})
            actions.append(doc)
        await self._es.bulk(body=actions)
        logger.info("Bulk indexed %d documents", len(docs))
