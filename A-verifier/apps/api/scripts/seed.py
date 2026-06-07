"""Seed initial : marchands connus. Run with: python -m apps.api.scripts.seed"""
import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.db.models import Merchant

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://app:changeme@postgres:5432/electronic_star",
)

MERCHANTS = [
    {
        "slug": "ldlc",
        "display_name": "LDLC",
        "base_url": "https://www.ldlc.com",
        "country_code": "FR",
        "crawl_policy": {"delay": 2.0, "concurrency": 1},
    },
    {
        "slug": "materiel",
        "display_name": "Materiel.net",
        "base_url": "https://www.materiel.net",
        "country_code": "FR",
        "crawl_policy": {"delay": 2.0, "concurrency": 1},
    },
]


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        for data in MERCHANTS:
            existing = await session.execute(
                select(Merchant).where(Merchant.slug == data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"  already exists: {data['slug']}")
                continue

            merchant = Merchant(id=uuid.uuid4(), **data)
            session.add(merchant)
            print(f"  inserted: {data['slug']}")

        await session.commit()

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
