BOT_NAME = "electronic_star"

SPIDER_MODULES = ["apps.crawler.src.spiders"]
NEWSPIDER_MODULE = "apps.crawler.src.spiders"

# Conformité robots.txt activée par défaut
ROBOTSTXT_OBEY = True

# Politesse par défaut — ajuster par domaine si nécessaire
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.5

# scrapy-playwright — rendu JS pour les sites avec anti-bot
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"


def should_abort_playwright_request(request):
    """Évite de charger les assets non utiles à l'extraction produit."""
    if request.resource_type in {"image", "font", "media"}:
        return True
    return any(
        host in request.url
        for host in (
            "googletagmanager.com",
            "google-analytics.com",
            "plausible.io",
            "tracking.groupe-ldlc.com",
        )
    )


PLAYWRIGHT_ABORT_REQUEST = should_abort_playwright_request

# HTTP
COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# Middlewares
DOWNLOADER_MIDDLEWARES = {
    "apps.crawler.src.middlewares.captcha.CaptchaDetectionMiddleware": 543,
}

# Pipeline de traitement
ITEM_PIPELINES = {
    "apps.crawler.src.pipelines.NormalizePipeline": 100,
    "apps.crawler.src.pipelines.PostgresPipeline": 200,
}

# Logs
LOG_LEVEL = "INFO"
