from pathlib import Path

from apps.crawler.scripts.run_spider import (
    build_settings,
    default_output_path,
    summarize_crawl_stats,
)


def test_default_output_path_uses_spider_name():
    assert default_output_path("materiel") == Path(
        "/app/apps/crawler/materiel_crawl_latest.json"
    )


def test_build_settings_exports_json_and_disables_pipelines_by_default():
    settings = build_settings(
        output=Path("/tmp/materiel.json"),
        itemcount=20,
        ingest=False,
        log_level="WARNING",
    )

    assert settings.get("FEEDS") == {
        "/tmp/materiel.json": {
            "format": "json",
            "encoding": "utf8",
            "overwrite": True,
        }
    }
    assert settings.getint("CLOSESPIDER_ITEMCOUNT") == 20
    assert settings.get("ITEM_PIPELINES") == {}
    assert settings.get("LOG_LEVEL") == "WARNING"


def test_build_settings_keeps_pipelines_when_ingesting():
    settings = build_settings(
        output=Path("/tmp/materiel.json"),
        itemcount=None,
        ingest=True,
        log_level="INFO",
    )

    assert "apps.crawler.src.pipelines.PostgresPipeline" in settings.get(
        "ITEM_PIPELINES"
    )


def test_summarize_crawl_stats_maps_scrapy_stats():
    summary = summarize_crawl_stats(
        {
            "item_scraped_count": 21,
            "downloader/response_count": 26,
            "downloader/response_status_count/200": 24,
            "downloader/response_status_count/429": 1,
            "downloader/response_status_count/403": 1,
            "downloader/exception_count": 2,
        }
    )

    assert summary == {
        "items_scraped": 21,
        "pages_ok": 24,
        "pages_failed": 4,
        "captcha_count": 1,
        "blocked_count": 1,
    }
