"""Spider Grosbill — PC, composants & périphériques.

Grosbill partage le même CMS qu'ASP.NET que Cybertek :
pages statiques, JSON-LD Product complet, même sélecteurs CSS.

SKU : identifiant numérique en fin d'URL, ex. -167902.aspx → '167902'.
"""
import json
import re

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

_SKU_RE = re.compile(r"-(\d{5,})\.aspx", re.I)


class GrosbillSpider(BaseProductSpider):
    name = "grosbill"
    merchant_slug = "grosbill"
    allowed_domains = ["www.grosbill.com"]

    start_urls = [
        "https://www.grosbill.com/pc-portable-40.aspx",
        "https://www.grosbill.com/ecran-pc-62.aspx",
        "https://www.grosbill.com/2-carte_graphique-cat-informatique",
        "https://www.grosbill.com/micro-casque-73.aspx",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 2.0,
        "DOWNLOAD_TIMEOUT": 30,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    PRODUCT_LINK_SEL = "a[class*='liste__produit__link']::attr(href)"
    NEXT_PAGE_SEL = "a[rel='next']::attr(href)"
    TITLE_SEL = "span[class*='title_fiche']::text"
    PRICE_SELECTORS = (
        "[itemprop='price']::attr(content)",
        "span[class*='prix']::text",
    )
    BRAND_SELECTORS = (
        "[itemprop='brand'] [itemprop='name']::text",
        "[itemprop='brand']::text",
    )
    GTIN_SELECTORS = (
        "[itemprop='gtin13']::attr(content)",
        "[itemprop='gtin']::attr(content)",
    )
    STOCK_SELECTORS = (
        "[itemprop='availability']::attr(href)",
        "link[itemprop='availability']::attr(href)",
        "[class*='availability']::text",
        "[class*='stock']::text",
    )

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self.errback_log)

    def extract_product_links(self, response) -> list[str]:
        hrefs = response.css("a::attr(href)").getall()
        return _dedupe_urls(
            response.urljoin(href)
            for href in hrefs
            if _SKU_RE.search(href)
        )

    def extract_next_page(self, response) -> str | None:
        href = response.css(self.NEXT_PAGE_SEL).get()
        if href and href != "#":
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
            yield scrapy.Request(url, callback=self.parse_product, errback=self.errback_log)

        next_page = self.extract_next_page(response)
        if next_page:
            yield scrapy.Request(next_page, callback=self.parse, errback=self.errback_log)

    def parse_product(self, response):
        item = self._from_json_ld(response) or self._from_css(response)
        if item:
            yield self.dump_item(item, response)

    def errback_log(self, failure):
        self.logger.error("Erreur Grosbill %s: %r", failure.request.url, failure.value)

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

            sku = _sku_from_url(response.url)
            if not sku:
                return None

            price = _price_from_offers(data.get("offers"))
            if price is None:
                return None

            return RawItem(
                merchant_slug=self.merchant_slug,
                merchant_sku=sku,
                product_url=response.url,
                source_title=(data.get("name") or "").strip(),
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
        sku = _sku_from_url(response.url)
        if not sku:
            self.logger.warning("SKU Grosbill introuvable : %s", response.url)
            return None

        title = response.css(self.TITLE_SEL).get("").strip()
        if not title:
            title = " ".join(response.css("h1 *::text").getall()).strip()
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


def _sku_from_url(url: str) -> str | None:
    m = _SKU_RE.search(url)
    return m.group(1) if m else None
