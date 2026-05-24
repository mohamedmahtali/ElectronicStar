import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import Merchant, Offer, PriceHistory, Product
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


class ProductMerchantOut(BaseModel):
    merchant_id: str
    merchant_slug: str
    merchant_name: str


class ProductDetailResponse(BaseModel):
    product_id: str
    canonical_key: str
    title: str
    brand: str | None
    gtin: str | None
    mpn: str | None
    category_path: str | None
    price_min: float | None
    price_max: float | None
    merchants: list[ProductMerchantOut]
    offers: list[OfferOut]


class PriceHistoryPointOut(BaseModel):
    offer_id: str
    merchant_id: str
    merchant_slug: str
    merchant_name: str
    captured_at: str
    price_amount: float
    shipping_amount: float
    total_amount: float
    availability: str


class PriceHistoryResponse(BaseModel):
    product_id: str
    points: list[PriceHistoryPointOut]


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product_detail(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    product, offers = await _load_product_and_offers(product_id, db)
    prices = [offer.price_amount for offer, _merchant in offers]
    merchants_by_id = {
        str(merchant.id): ProductMerchantOut(
            merchant_id=str(merchant.id),
            merchant_slug=merchant.slug,
            merchant_name=merchant.display_name,
        )
        for _offer, merchant in offers
    }

    return ProductDetailResponse(
        product_id=str(product.id),
        canonical_key=product.canonical_key,
        title=product.title_display,
        brand=product.brand_norm,
        gtin=product.gtin,
        mpn=product.mpn,
        category_path=product.category_path,
        price_min=float(min(prices)) if prices else None,
        price_max=float(max(prices)) if prices else None,
        merchants=list(merchants_by_id.values()),
        offers=_serialize_offers(offers),
    )


@router.get("/{product_id}/price-history", response_model=PriceHistoryResponse)
async def get_product_price_history(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    product = await _load_product(product_id, db)
    rows = await _load_price_history(product_id, db)

    return PriceHistoryResponse(
        product_id=str(product.id),
        points=_serialize_price_history(rows),
    )


@router.get("/{product_id}/offers", response_model=OffersResponse)
async def get_product_offers(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    _product, offers = await _load_product_and_offers(product_id, db)

    return OffersResponse(
        product_id=str(product_id),
        offers=_serialize_offers(offers),
    )


async def _load_product_and_offers(
    product_id: uuid.UUID, db: AsyncSession
) -> tuple[Product, list[tuple[Offer, Merchant]]]:
    product = await _load_product(product_id, db)

    offers_result = await db.execute(
        select(Offer, Merchant)
        .join(Merchant, Merchant.id == Offer.merchant_id)
        .where(Offer.product_id == product_id)
        .order_by(Offer.price_amount)
    )
    offers = list(offers_result.all())
    return product, offers


async def _load_product(product_id: uuid.UUID, db: AsyncSession) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return product


async def _load_price_history(
    product_id: uuid.UUID, db: AsyncSession
) -> list[tuple[PriceHistory, Offer, Merchant]]:
    result = await db.execute(
        select(PriceHistory, Offer, Merchant)
        .join(Offer, Offer.id == PriceHistory.offer_id)
        .join(Merchant, Merchant.id == Offer.merchant_id)
        .where(Offer.product_id == product_id)
        .order_by(PriceHistory.captured_at, Merchant.slug, Offer.id)
    )
    return list(result.all())


def _serialize_offers(offers: list[tuple[Offer, Merchant]]) -> list[OfferOut]:
    return [
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
    ]


def _serialize_price_history(
    rows: list[tuple[PriceHistory, Offer, Merchant]],
) -> list[PriceHistoryPointOut]:
    return [
        PriceHistoryPointOut(
            offer_id=str(offer.id),
            merchant_id=str(merchant.id),
            merchant_slug=merchant.slug,
            merchant_name=merchant.display_name,
            captured_at=history.captured_at.isoformat(),
            price_amount=float(history.price_amount),
            shipping_amount=float(history.shipping_amount),
            total_amount=float(history.price_amount + history.shipping_amount),
            availability=history.availability,
        )
        for history, offer, merchant in rows
    ]
