from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.db.models import Merchant
from apps.api.src.db.session import get_db
from apps.api.src.search.es_client import get_es_client
from apps.api.src.search.es_mappings import PRODUCTS_INDEX_READ_ALIAS

router = APIRouter(prefix="/search", tags=["search"])


class SearchMerchantOut(BaseModel):
    merchant_id: str
    merchant_slug: str
    merchant_name: str


class ProductSearchItem(BaseModel):
    product_id: str
    canonical_key: str
    title: str
    brand: str | None
    price_min: float | None
    price_max: float | None
    merchant_ids: list[str]
    merchants: list[SearchMerchantOut]


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[ProductSearchItem]


@router.get("/products", response_model=SearchResponse)
async def search_products(
    q: Annotated[str, Query(min_length=1, description="Requête texte")],
    brand: str | None = None,
    merchant: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    es=Depends(get_es_client),
    db: AsyncSession = Depends(get_db),
):
    must = [{"multi_match": {"query": q, "fields": ["title^2", "brand"]}}]
    filters = []

    if brand:
        filters.append({"term": {"brand": brand}})
    if merchant:
        merchant_filter_id = await _resolve_merchant_id(db, merchant)
        filters.append({"term": {"merchant_ids": merchant_filter_id or merchant}})
    if min_price is not None or max_price is not None:
        price_range: dict = {}
        if min_price is not None:
            price_range["gte"] = min_price
        if max_price is not None:
            price_range["lte"] = max_price
        filters.append({"range": {"price_min": price_range}})

    query = {"bool": {"must": must, "filter": filters}} if filters else {"bool": {"must": must}}

    result = await es.search(
        index=PRODUCTS_INDEX_READ_ALIAS,
        body={
            "query": query,
            "from": (page - 1) * size,
            "size": size,
        },
    )

    hits = result["hits"]
    merchant_ids = {
        merchant_id
        for hit in hits["hits"]
        for merchant_id in hit["_source"].get("merchant_ids", [])
    }
    merchants_by_id = await _merchant_lookup(db, merchant_ids)
    items = [
        ProductSearchItem(
            product_id=h["_source"].get("product_id", h["_id"]),
            canonical_key=h["_source"].get("canonical_key", ""),
            title=h["_source"].get("title", ""),
            brand=h["_source"].get("brand"),
            price_min=h["_source"].get("price_min"),
            price_max=h["_source"].get("price_max"),
            merchant_ids=h["_source"].get("merchant_ids", []),
            merchants=[
                merchants_by_id[merchant_id]
                for merchant_id in h["_source"].get("merchant_ids", [])
                if merchant_id in merchants_by_id
            ],
        )
        for h in hits["hits"]
    ]

    return SearchResponse(total=hits["total"]["value"], page=page, size=size, items=items)


async def _resolve_merchant_id(db: AsyncSession, merchant: str) -> str | None:
    row = await db.execute(select(Merchant.id).where(Merchant.slug == merchant))
    merchant_id = row.scalar_one_or_none()
    return str(merchant_id) if merchant_id else None


async def _merchant_lookup(
    db: AsyncSession, merchant_ids: set[str]
) -> dict[str, SearchMerchantOut]:
    if not merchant_ids:
        return {}

    row = await db.execute(select(Merchant).where(Merchant.id.in_(merchant_ids)))
    merchants = row.scalars().all()
    return {
        str(merchant.id): SearchMerchantOut(
            merchant_id=str(merchant.id),
            merchant_slug=merchant.slug,
            merchant_name=merchant.display_name,
        )
        for merchant in merchants
    }
