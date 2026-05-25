"""Minimal periodic crawler scheduler.

This intentionally stays small: it shells out to run_spider so each crawl gets
a fresh Scrapy/Twisted process.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import redis

DEFAULT_REQUEST_QUEUE = "crawler:run_requests"


def build_run_command(
    *,
    merchant: str,
    itemcount: int | None,
    output_dir: Path,
    ingest: bool,
    log_level: str,
    output: Path | None = None,
    crawl_run_id: str | None = None,
) -> list[str]:
    output = output or output_dir / f"{merchant}_scheduled_latest.json"
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
    if crawl_run_id:
        command.extend(["--crawl-run-id", crawl_run_id])
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
    request_queue: str,
    request_poll_seconds: float,
) -> None:
    interval_seconds = interval_minutes * 60
    run_number = 0
    redis_client = _create_redis_client()

    while iterations is None or run_number < iterations:
        _run_pending_requests(
            redis_client=redis_client,
            request_queue=request_queue,
            output_dir=output_dir,
            default_itemcount=itemcount,
            default_log_level=log_level,
        )

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
        _sleep_with_request_polling(
            redis_client=redis_client,
            request_queue=request_queue,
            output_dir=output_dir,
            default_itemcount=itemcount,
            default_log_level=log_level,
            interval_seconds=interval_seconds,
            poll_seconds=request_poll_seconds,
        )


def _sleep_with_request_polling(
    *,
    redis_client,
    request_queue: str,
    output_dir: Path,
    default_itemcount: int | None,
    default_log_level: str,
    interval_seconds: float,
    poll_seconds: float,
) -> None:
    deadline = time.monotonic() + interval_seconds
    while time.monotonic() < deadline:
        _run_pending_requests(
            redis_client=redis_client,
            request_queue=request_queue,
            output_dir=output_dir,
            default_itemcount=default_itemcount,
            default_log_level=default_log_level,
        )
        remaining = deadline - time.monotonic()
        time.sleep(max(0.0, min(poll_seconds, remaining)))


def _run_pending_requests(
    *,
    redis_client,
    request_queue: str,
    output_dir: Path,
    default_itemcount: int | None,
    default_log_level: str,
) -> None:
    if redis_client is None:
        return

    while True:
        payload = _pop_request(redis_client, request_queue)
        if payload is None:
            return
        command = _command_from_request(
            payload,
            output_dir=output_dir,
            default_itemcount=default_itemcount,
            default_log_level=default_log_level,
        )
        print(f"Starting requested crawl: {' '.join(command)}", flush=True)
        subprocess.run(command, check=False)


def _command_from_request(
    payload: dict,
    *,
    output_dir: Path,
    default_itemcount: int | None,
    default_log_level: str,
) -> list[str]:
    merchant = payload["merchant"]
    crawl_run_id = payload.get("crawl_run_id")
    output = Path(
        payload.get("output")
        or output_dir / f"{merchant}_manual_{str(crawl_run_id)[:8]}.json"
    )
    itemcount = payload.get("itemcount", default_itemcount)
    log_level = payload.get("log_level") or default_log_level
    ingest = bool(payload.get("ingest", True))

    return build_run_command(
        merchant=merchant,
        itemcount=itemcount,
        output_dir=output_dir,
        ingest=ingest,
        log_level=log_level,
        output=output,
        crawl_run_id=crawl_run_id,
    )


def _create_redis_client():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        return redis.Redis.from_url(redis_url, decode_responses=True)
    except redis.RedisError as exc:
        print(f"Redis request queue unavailable: {type(exc).__name__}: {exc}", flush=True)
        return None


def _pop_request(redis_client, request_queue: str) -> dict | None:
    try:
        raw = redis_client.lpop(request_queue)
    except redis.RedisError as exc:
        print(f"Redis request queue unavailable: {type(exc).__name__}: {exc}", flush=True)
        return None

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("Skipping invalid crawl request payload", flush=True)
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merchant", required=True, help="Spider/merchant name")
    parser.add_argument("--interval-minutes", type=float, default=60.0)
    parser.add_argument("--itemcount", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("/app/apps/crawler/scheduled"))
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--request-queue", default=DEFAULT_REQUEST_QUEUE)
    parser.add_argument("--request-poll-seconds", type=float, default=5.0)
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
        request_queue=args.request_queue,
        request_poll_seconds=args.request_poll_seconds,
    )


if __name__ == "__main__":
    main()
