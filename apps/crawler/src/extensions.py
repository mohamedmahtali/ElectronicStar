"""Scrapy extension: push crawl stats to Prometheus Pushgateway at spider close."""
import logging
import os

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class PrometheusPushExtension:
    def __init__(self, pushgateway_url: str):
        self._url = pushgateway_url

    @classmethod
    def from_crawler(cls, crawler):
        url = os.getenv("PROMETHEUS_PUSHGATEWAY_URL", "")
        if not url:
            raise NotConfigured("PROMETHEUS_PUSHGATEWAY_URL not set — skipping metrics push")
        ext = cls(url)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_closed(self, spider, reason):
        try:
            from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

            stats = spider.crawler.stats.get_stats()
            merchant = getattr(spider, "merchant_slug", spider.name)
            registry = CollectorRegistry()

            def g(name, doc, value):
                gauge = Gauge(name, doc, ["merchant"], registry=registry)
                gauge.labels(merchant=merchant).set(value)

            g("crawl_pages_ok_total", "Pages OK", stats.get("response_received_count", 0))
            g(
                "crawl_pages_failed_total",
                "Pages en erreur",
                stats.get("downloader/exception_count", 0),
            )
            g("crawl_items_scraped_total", "Items ingérés", stats.get("item_scraped_count", 0))
            g("crawl_captcha_total", "CAPTCHAs détectés", stats.get("captcha_detected", 0))
            g(
                "crawl_blocked_total",
                "Requêtes bloquées (403/429)",
                stats.get("httperror/response_status_count/403", 0)
                + stats.get("httperror/response_status_count/429", 0),
            )

            start = stats.get("start_time")
            finish = stats.get("finish_time")
            duration = (finish - start).total_seconds() if start and finish else 0.0
            g("crawl_duration_seconds", "Durée du crawl", duration)

            success_ratio = 0.0
            total = stats.get("response_received_count", 0)
            if total > 0:
                failed = stats.get("downloader/exception_count", 0)
                success_ratio = (total - failed) / total
            g("crawl_success_ratio", "Ratio pages OK / total", success_ratio)

            push_to_gateway(self._url, job=f"crawler_{merchant}", registry=registry)
            logger.info("Metrics pushed to Pushgateway for merchant=%s reason=%s", merchant, reason)
        except Exception as exc:
            logger.warning("Could not push metrics to Pushgateway: %s", exc)
