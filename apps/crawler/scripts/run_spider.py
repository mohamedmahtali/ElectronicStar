"""Run a crawler spider with a JSON export.

Examples inside the crawler container:
python -m apps.crawler.scripts.run_spider materiel --itemcount 20
python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --ingest
"""
import argparse
import os
from pathlib import Path

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings


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


def run_spider(
    *,
    spider: str,
    output: Path,
    itemcount: int | None,
    ingest: bool,
    log_level: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    settings = build_settings(
        output=output,
        itemcount=itemcount,
        ingest=ingest,
        log_level=log_level,
    )
    process = CrawlerProcess(settings)
    process.crawl(spider)
    process.start()
    print(f"Crawl finished: spider={spider} output={output} ingest={ingest}")


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
    )


if __name__ == "__main__":
    main()
