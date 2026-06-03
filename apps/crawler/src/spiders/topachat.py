"""Spider Top Achat — PC portables, GPU, écrans, composants.

TopAchat (groupe LDLC) : pages statiques, JSON-LD Product en liste.
Catalogue de ~80 produits par catégorie sur une seule page (pas de pagination).

SKU : identifiant numérique en fin d'URL, ex. ref_est_in20031672 → 'in20031672'.
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

# ex. ref_est_in20031672.html → groupe 1 = 'in20031672'
_SKU_RE = re.compile(r"ref_est_(in\d+)", re.I)


class TopAchatSpider(BaseProductSpider):
    name = "topachat"
    merchant_slug = "topachat"
    allowed_domains = ["www.topachat.com"]

    start_urls = [
        "https://www.topachat.com/pages/produits_cat_est_ordinateurs_puis_rubrique_est_wport.html",
        "https://www.topachat.com/pages/produits_cat_est_micro_puis_rubrique_est_wgfx_pcie.html",
        "https://www.topachat.com/pages/produits_cat_est_peripheriques_puis_rubrique_est_w_moni.html",
        "https://www.topachat.com/pages/produits_cat_est_micro_puis_rubrique_est_w_ssd.html",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 2.0,
        "DOWNLOAD_TIMEOUT": 30,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    TITLE_SEL = "h1::text"
    PRICE_SELECTORS = (
        "[itemprop='price']::attr(content)",
        "span[class*='prix']::text",
        "[class*='price']::text",
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

    def parse_product(self, response):
        item = self._from_json_ld(response) or self._from_css(response)
        if item:
            yield self.dump_item(item, response)

    def errback_log(self, failure):
        self.logger.error("Erreur TopAchat %s: %r", failure.request.url, failure.value)

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
            self.logger.warning("SKU TopAchat introuvable : %s", response.url)
            return None

        title = " ".join(response.css(self.TITLE_SEL).getall()).strip()
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
