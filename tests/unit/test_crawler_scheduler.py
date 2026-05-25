from pathlib import Path

from apps.crawler.scripts.scheduler import _command_from_request, build_run_command


def test_build_run_command_without_ingest():
    command = build_run_command(
        merchant="materiel",
        itemcount=20,
        output_dir=Path("/tmp/crawls"),
        ingest=False,
        log_level="INFO",
    )

    assert command[1:4] == ["-m", "apps.crawler.scripts.run_spider", "materiel"]
    assert "--itemcount" in command
    assert "20" in command
    assert "--ingest" not in command
    assert "/tmp/crawls/materiel_scheduled_latest.json" in command


def test_build_run_command_uses_merchant_in_output_name():
    command = build_run_command(
        merchant="ldlc",
        itemcount=20,
        output_dir=Path("/tmp/crawls"),
        ingest=False,
        log_level="INFO",
    )

    assert command[1:4] == ["-m", "apps.crawler.scripts.run_spider", "ldlc"]
    assert "/tmp/crawls/ldlc_scheduled_latest.json" in command


def test_build_run_command_with_ingest():
    command = build_run_command(
        merchant="materiel",
        itemcount=None,
        output_dir=Path("/tmp/crawls"),
        ingest=True,
        log_level="WARNING",
    )

    assert "--itemcount" not in command
    assert "--ingest" in command
    assert command[-1] == "--ingest"


def test_build_run_command_with_existing_crawl_run():
    command = build_run_command(
        merchant="materiel",
        itemcount=5,
        output_dir=Path("/tmp/crawls"),
        ingest=True,
        log_level="INFO",
        output=Path("/tmp/crawls/manual.json"),
        crawl_run_id="abc-123",
    )

    assert "/tmp/crawls/manual.json" in command
    assert "--crawl-run-id" in command
    assert "abc-123" in command
    assert command[-1] == "--ingest"


def test_command_from_request_builds_manual_crawl():
    command = _command_from_request(
        {
            "merchant": "materiel",
            "crawl_run_id": "run-123",
            "itemcount": 7,
            "output": "/tmp/crawls/manual.json",
            "ingest": True,
        },
        output_dir=Path("/tmp/crawls"),
        default_itemcount=20,
        default_log_level="INFO",
    )

    assert "materiel" in command
    assert "/tmp/crawls/manual.json" in command
    assert "--crawl-run-id" in command
    assert "run-123" in command
    assert "--itemcount" in command
    assert "7" in command
