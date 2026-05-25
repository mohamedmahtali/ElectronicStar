"""Minimal periodic crawler scheduler.

This intentionally stays small: it shells out to run_spider so each crawl gets
a fresh Scrapy/Twisted process.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path


def build_run_command(
    *,
    merchant: str,
    itemcount: int | None,
    output_dir: Path,
    ingest: bool,
    log_level: str,
) -> list[str]:
    output = output_dir / f"{merchant}_scheduled_latest.json"
    command = [
        sys.executable,
        "-m",
        "apps.crawler.scripts.run_spider",
        merchant,
        "--output",
        str(output),
        "--log-level",
        log_level,
    ]
    if itemcount is not None:
        command.extend(["--itemcount", str(itemcount)])
    if ingest:
        command.append("--ingest")
    return command


def run_scheduler(
    *,
    merchant: str,
    interval_minutes: float,
    itemcount: int | None,
    output_dir: Path,
    ingest: bool,
    log_level: str,
    iterations: int | None,
) -> None:
    interval_seconds = interval_minutes * 60
    run_number = 0

    while iterations is None or run_number < iterations:
        run_number += 1
        command = build_run_command(
            merchant=merchant,
            itemcount=itemcount,
            output_dir=output_dir,
            ingest=ingest,
            log_level=log_level,
        )
        print(f"Starting scheduled crawl #{run_number}: {' '.join(command)}", flush=True)
        subprocess.run(command, check=False)

        if iterations is not None and run_number >= iterations:
            break
        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merchant", required=True, help="Spider/merchant name")
    parser.add_argument("--interval-minutes", type=float, default=60.0)
    parser.add_argument("--itemcount", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("/app/apps/crawler/scheduled"))
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Optional finite run count for demos/tests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_scheduler(
        merchant=args.merchant,
        interval_minutes=args.interval_minutes,
        itemcount=args.itemcount,
        output_dir=args.output_dir,
        ingest=args.ingest,
        log_level=args.log_level,
        iterations=args.iterations,
    )


if __name__ == "__main__":
    main()
