from pathlib import Path

from apps.crawler.scripts.scheduler import build_run_command


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
