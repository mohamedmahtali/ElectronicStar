"""Run a crawler spider with a JSON export.

Examples inside the crawler container:
python -m apps.crawler.scripts.run_spider materiel --itemcount 20
python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --ingest
"""
import argparse
import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.src.db.models import CrawlRun, Merchant


def default_output_path(spider: str) -> Path:
    return Path(f"/app/apps/crawler/{spider}_crawl_latest.json")


def build_settings(
    *,
    output: Path,
    itemcount: int | None,
    ingest: bool,
    log_level: str,
) -> Settings:
    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "apps.crawler.settings")
    settings = get_project_settings()
    settings.set(
        "FEEDS",
        {
            str(output): {
                "format": "json",
                "encoding": "utf8",
                "overwrite": True,
            }
        },
        priority="cmdline",
    )
    settings.set("LOG_LEVEL", log_level, priority="cmdline")

    if itemcount is not None:
        settings.set("CLOSESPIDER_ITEMCOUNT", itemcount, priority="cmdline")

    if not ingest:
        settings.set("ITEM_PIPELINES", {}, priority="cmdline")

    return settings


def summarize_crawl_stats(stats: dict) -> dict[str, int]:
    response_count = _int_stat(stats, "downloader/response_count")
    pages_ok = _int_stat(stats, "downloader/response_status_count/200")
    exception_count = _int_stat(stats, "downloader/exception_count")

    return {
        "items_scraped": _int_stat(stats, "item_scraped_count"),
        "pages_ok": pages_ok,
        "pages_failed": max(response_count - pages_ok, 0) + exception_count,
        "captcha_count": _int_stat(stats, "downloader/response_status_count/429"),
        "blocked_count": _int_stat(stats, "downloader/response_status_count/403"),
    }


def _int_stat(stats: dict, key: str) -> int:
    value = stats.get(key, 0)
    return int(value or 0)


def run_spider(
    *,
    spider: str,
    output: Path,
    itemcount: int | None,
    ingest: bool,
    log_level: str,
    status_log: bool | None = None,
    crawl_run_id: uuid.UUID | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    should_log_status = crawl_run_id is not None or (ingest if status_log is None else status_log)
    run_id = (
        _safe_start_crawl_run(
            crawl_run_id=crawl_run_id,
            spider=spider,
            output=output,
            ingest=ingest,
        )
        if should_log_status
        else None
    )
    settings = build_settings(
        output=output,
        itemcount=itemcount,
        ingest=ingest,
        log_level=log_level,
    )
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(spider)
    error_message = None
    status = "success"

    try:
        process.crawl(crawler)
        process.start()
    except Exception as exc:
        status = "failed"
        error_message = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stats = crawler.stats.get_stats()
        _safe_finish_crawl_run(
            run_id=run_id,
            status=status,
            stats=stats,
            error_message=error_message,
        )

    print(f"Crawl finished: spider={spider} output={output} ingest={ingest}")


def _safe_start_crawl_run(
    *,
    crawl_run_id: uuid.UUID | None,
    spider: str,
    output: Path,
    ingest: bool,
) -> uuid.UUID | None:
    try:
        if crawl_run_id is not None:
            return asyncio.run(
                _start_existing_crawl_run(
                    crawl_run_id=crawl_run_id,
                    output=output,
                    ingest=ingest,
                )
            )
        return asyncio.run(
            _create_crawl_run(
                spider=spider,
                output=output,
                ingest=ingest,
            )
        )
    except Exception as exc:
        print(
            "Crawl status logging unavailable at start: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def _safe_finish_crawl_run(
    *,
    run_id: uuid.UUID | None,
    status: str,
    stats: dict,
    error_message: str | None,
) -> None:
    if run_id is None:
        return
    try:
        asyncio.run(
            _finish_crawl_run(
                run_id=run_id,
                status=status,
                stats=stats,
                error_message=error_message,
            )
        )
    except Exception as exc:
        print(
            "Crawl status logging unavailable at finish: "
            f"{type(exc).__name__}: {exc}"
        )


async def _create_crawl_run(
    *,
    spider: str,
    output: Path,
    ingest: bool,
) -> uuid.UUID | None:
    engine = _create_status_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            merchant_id = await session.scalar(
                select(Merchant.id).where(Merchant.slug == spider)
            )
            if merchant_id is None:
                return None

            run = CrawlRun(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                run_type="full" if ingest else "export",
                status="running",
                ingest_enabled=ingest,
                output_path=str(output),
            )
            session.add(run)
            await session.commit()
            return run.id
    finally:
        await engine.dispose()


async def _start_existing_crawl_run(
    *,
    crawl_run_id: uuid.UUID,
    output: Path,
    ingest: bool,
) -> uuid.UUID:
    engine = _create_status_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await session.execute(
                update(CrawlRun)
                .where(CrawlRun.id == crawl_run_id)
                .values(
                    started_at=datetime.now(UTC),
                    ended_at=None,
                    status="running",
                    items_scraped=0,
                    pages_ok=0,
                    pages_failed=0,
                    captcha_count=0,
                    blocked_count=0,
                    ingest_enabled=ingest,
                    output_path=str(output),
                    error_message=None,
                )
            )
            await session.commit()
            return crawl_run_id
    finally:
        await engine.dispose()


async def _finish_crawl_run(
    *,
    run_id: uuid.UUID,
    status: str,
    stats: dict,
    error_message: str | None,
) -> None:
    summary = summarize_crawl_stats(stats)
    engine = _create_status_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await session.execute(
                update(CrawlRun)
                .where(CrawlRun.id == run_id)
                .values(
                    ended_at=datetime.now(UTC),
                    status=status,
                    error_message=error_message,
                    **summary,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


def _database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:changeme@postgres:5432/electronic_star",
    )


def _create_status_engine():
    return create_async_engine(
        _database_url(),
        pool_pre_ping=True,
        connect_args={"timeout": 2},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("spider", help="Spider name, for example: materiel or ldlc")
    parser.add_argument("--itemcount", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Keep Scrapy item pipelines enabled to persist items in DB/ES.",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--status-log",
        action="store_true",
        help="Record this crawl in the crawl_runs status table.",
    )
    parser.add_argument(
        "--crawl-run-id",
        type=uuid.UUID,
        default=None,
        help="Update an existing crawl_runs row instead of creating a new one.",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = default_output_path(args.spider)
    return args


def main() -> None:
    args = parse_args()
    run_spider(
        spider=args.spider,
        output=args.output,
        itemcount=args.itemcount,
        ingest=args.ingest,
        log_level=args.log_level,
        status_log=args.status_log or args.ingest,
        crawl_run_id=args.crawl_run_id,
    )


if __name__ == "__main__":
    main()
