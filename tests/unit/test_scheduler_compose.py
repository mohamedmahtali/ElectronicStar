from pathlib import Path


def test_docker_compose_defines_supervised_materiel_scheduler():
    compose = Path("docker-compose.yml").read_text()

    assert "crawler-scheduler-materiel:" in compose
    assert "profiles:" in compose
    assert "- scheduler" in compose
    assert "restart: unless-stopped" in compose
    assert "apps.crawler.scripts.scheduler" in compose
    assert "--merchant" in compose
    assert "materiel" in compose
    assert "--request-queue" in compose
    assert "--ingest" in compose


def test_makefile_exposes_scheduler_targets():
    makefile = Path("Makefile").read_text()

    assert "scheduler-materiel-up:" in makefile
    assert "scheduler-materiel-down:" in makefile
    assert "scheduler-materiel-logs:" in makefile
