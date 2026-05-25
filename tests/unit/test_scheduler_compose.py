from pathlib import Path


def test_docker_compose_defines_supervised_schedulers():
    compose = Path("docker-compose.yml").read_text()

    assert "crawler-scheduler-materiel:" in compose
    assert "crawler-scheduler-ldlc:" in compose
    assert "profiles:" in compose
    assert "- scheduler" in compose
    assert "restart: unless-stopped" in compose
    assert "apps.crawler.scripts.scheduler" in compose
    assert "--merchant" in compose
    assert "materiel" in compose
    assert "ldlc" in compose
    assert "--request-queue" in compose
    assert "--ingest" in compose
    assert "CRAWLER_MATERIEL_INTERVAL_MINUTES" in compose
    assert "CRAWLER_LDLC_INTERVAL_MINUTES" in compose
    assert "crawler:run_requests:materiel" in compose
    assert "crawler:run_requests:ldlc" in compose


def test_makefile_exposes_scheduler_targets():
    makefile = Path("Makefile").read_text()

    assert "scheduler-materiel-up:" in makefile
    assert "scheduler-materiel-down:" in makefile
    assert "scheduler-materiel-logs:" in makefile
    assert "scheduler-ldlc-up:" in makefile
    assert "scheduler-ldlc-down:" in makefile
    assert "scheduler-ldlc-logs:" in makefile
    assert "scheduler-up:" in makefile
    assert "scheduler-down:" in makefile
