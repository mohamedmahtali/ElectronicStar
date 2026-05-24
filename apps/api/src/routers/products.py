import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import Merchant, Offer, Product
from apps.api.src.db.session import get_db

router = APIRouter(prefix="/products", tags=["products"])


class OfferOut(BaseModel):
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    seller_name: str | None
    price_amount: float
    shipping_amount: float
    availability: str
    condition: str
    product_url: str
    last_seen_at: str


class OffersResponse(BaseModel):
    product_id: str
    offers: list[OfferOut]


@router.get("/{product_id}/offers", response_model=OffersResponse)
async def get_product_offers(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    offers_result = await db.execute(
        select(Offer, Merchant)
        .join(Merchant, Merchant.id == Offer.merchant_id)
        .where(Offer.product_id == product_id)
        .order_by(Offer.price_amount)
    )
    offers = offers_result.all()

    return OffersResponse(
        product_id=str(product_id),
        offers=[
            OfferOut(
                merchant_id=str(offer.merchant_id),
                merchant_slug=merchant.slug,
                merchant_name=merchant.display_name,
                seller_name=offer.seller_name,
                price_amount=float(offer.price_amount),
                shipping_amount=float(offer.shipping_amount),
                availability=offer.availability,
                condition=offer.condition,
                product_url=offer.product_url,
                last_seen_at=offer.last_seen_at.isoformat(),
            )
            for offer, merchant in offers
        ],
    )
