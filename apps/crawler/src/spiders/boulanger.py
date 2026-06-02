"""Spider Boulanger — électronique, informatique & son.

Boulanger ne nécessite pas Playwright : les pages listing et produit sont
entièrement rendues côté serveur (HTML statique). JSON-LD Product complet.

SKU : référence numérique extraite de l'URL (/ref/{id}).
"""
import html as html_mod
import json
import re
from decimal import Decimal, InvalidOperation

import scrapy

from libs.crawling.schemas import RawItem

from .base import BaseProductSpider
from .ldlc import (
    _availability_from_offers,
    _availability_from_text,
    _brand_from_ld,
    _dedupe_urls,
    _find_product_ld,
    _first_price_text,
    _first_text,
    _flatten,
    _parse_price,
    _price_from_offers,
)

# Référence produit Boulanger : /ref/ suivi de 5+ chiffres, ex. /ref/1222397
_REF_RE = re.compile(r"/ref/(\d{5,})", re.I)


class BoulangerSpider(BaseProductSpider):
    name = "boulanger"
    merchant_slug = "boulanger"
    allowed_domains = ["www.boulanger.com"]

    start_urls = [
        "https://www.boulanger.com/c/tous-les-ordinateurs-portables",
        "https://www.boulanger.com/c/smartphone-telephone-portable",
        "https://www.boulanger.com/c/televiseur",
        "https://www.boulanger.com/c/tous-les-casques-audio",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.5,
        "DOWNLOAD_TIMEOUT": 30,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        # Boulanger CDN envoie du Brotli quand il voit un UA Chrome,
        # mais Scrapy ne supporte pas br sans package externe.
        "DEFAULT_REQUEST_HEADERS": {
            **BaseProductSpider.custom_settings.get("DEFAULT_REQUEST_HEADERS", {}),
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
    }

    TITLE_SEL = "h1::text"
    PRICE_SELECTORS = (
        "[itemprop='price']::attr(content)",
        "[class*='price'] [class*='amount']::text",
        "[class*='Price'] strong::text",
    )
    BRAND_SELECTORS = (
        "[itemprop='brand'] [itemprop='name']::text",
        "[itemprop='brand']::text",
        "span[class*='brand']::text",
    )
    GTIN_SELECTORS = (
        "[itemprop='gtin13']::attr(content)",
        "[itemprop='gtin']::attr(content)",
        "meta[property='product:ean']::attr(content)",
    )
    STOCK_SELECTORS = (
        "[itemprop='availability']::attr(href)",
        "link[itemprop='availability']::attr(href)",
        "[class*='availability']::text",
        "[class*='stock']::text",
    )

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                errback=self.errback_log,
            )

    def extract_product_links(self, response) -> list[str]:
        hrefs = response.css("a::attr(href)").getall()
        return _dedupe_urls(
            response.urljoin(href)
            for href in hrefs
            if _REF_RE.search(href)
        )

    def extract_next_page(self, response) -> str | None:
        href = response.css(
            "a[rel='next']::attr(href), "
            "a.next::attr(href)"
        ).get()
        if href:
            return response.urljoin(href)
        return None

    def parse(self, response):
        links = self.extract_product_links(response)
        if not links:
            self.logger.warning(
                "Aucun lien produit extrait sur %s (status=%s)",
                response.url,
                response.status,
            )

        for url in links:
            yield scrapy.Request(
                url,
                callback=self.parse_product,
                errback=self.errback_log,
            )

        next_page = self.extract_next_page(response)
        if next_page:
            yield scrapy.Request(
                next_page,
                callback=self.parse,
                errback=self.errback_log,
            )

    def parse_product(self, response):
        item = self._from_json_ld(response) or self._from_css(response)
        if item:
            yield self.dump_item(item, response)

    def errback_log(self, failure):
        request = failure.request
        self.logger.error("Erreur Boulanger %s: %r", request.url, failure.value)

    # ------------------------------------------------------------------
    # JSON-LD (source principale)
    # ------------------------------------------------------------------

    def _from_json_ld(self, response) -> RawItem | None:
        for raw in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            data = _find_product_ld(data)
            if data is None:
                continue

            sku = _ref_from_url(response.url)
            if not sku:
                return None

            price = _boulanger_price(data.get("offers"))
            if price is None:
                return None

            return RawItem(
                merchant_slug=self.merchant_slug,
                merchant_sku=sku,
                product_url=response.url,
                source_title=html_mod.unescape((data.get("name") or "").strip()),
                brand_raw=_brand_from_ld(data),
                price_amount=price,
                availability=_availability_from_offers(data.get("offers")),
                gtin=data.get("gtin13") or data.get("gtin") or None,
                mpn=data.get("mpn") or None,
            )
        return None

    # ------------------------------------------------------------------
    # CSS fallback
    # ------------------------------------------------------------------

    def _from_css(self, response) -> RawItem | None:
        sku = _ref_from_url(response.url)
        if not sku:
            self.logger.warning("Référence Boulanger introuvable : %s", response.url)
            return None

        title = " ".join(response.css(self.TITLE_SEL).getall()).strip()
        if not title:
            self.logger.warning("Titre manquant sur %s", response.url)
            return None

        price_raw = _first_price_text(
            _flatten(response.css(sel).getall() for sel in self.PRICE_SELECTORS)
        )
        if not price_raw:
            price_raw = _first_price_text(response.css("body ::text").getall())
        price = _parse_price(price_raw)
        if price is None:
            self.logger.warning("Prix manquant sur %s", response.url)
            return None

        stock_text = _first_text(
            response.css(sel).getall() for sel in self.STOCK_SELECTORS
        ).lower()
        availability = _availability_from_text(
            stock_text or " ".join(response.css("body ::text").getall()).lower()
        )

        return RawItem(
            merchant_slug=self.merchant_slug,
            merchant_sku=sku,
            product_url=response.url,
            source_title=title,
            brand_raw=_first_text(
                response.css(sel).getall() for sel in self.BRAND_SELECTORS
            ) or None,
            price_amount=price,
            availability=availability,
            gtin=_first_text(
                response.css(sel).getall() for sel in self.GTIN_SELECTORS
            ) or None,
        )


def _ref_from_url(url: str) -> str | None:
    m = _REF_RE.search(url)
    return m.group(1) if m else None


def _boulanger_price(offers) -> Decimal | None:
    """Extends _price_from_offers to handle Boulanger's bare float strings like '1519.0'."""
    if not offers:
        return None
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None
    for key in ("price", "lowPrice", "highPrice"):
        raw = str(offers.get(key, "")).strip()
        if not raw:
            continue
        # Direct Decimal handles "1519.0", "499.99", "1299" without needing the euro regex
        try:
            val = Decimal(raw)
            if val > 0:
                return val
        except InvalidOperation:
            pass
        price = _parse_price(raw)
        if price is not None:
            return price
    return None
