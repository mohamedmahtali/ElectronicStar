"""Spider Fnac — électronique, informatique & son.

Stratégie :
  1. Parcourt les pages de catégorie via Playwright (domcontentloaded)
  2. Sur chaque fiche produit, attend networkidle puis tente JSON-LD schema.org/Product
  3. Repli sur sélecteurs CSS si le JSON-LD est absent ou incomplet

Anti-bot : Fnac utilise DataDome. playwright-stealth patche les fingerprints headless
(navigator.webdriver, etc.) avant chaque navigation via playwright_page_init_callback.
Escalader vers proxies résidentiels si DataDome évolue.
"""
import json
import re

import scrapy
from playwright_stealth import Stealth

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

# SKU Fnac : /a suivi de 6+ chiffres, ex. /a16428375/
_SKU_RE = re.compile(r"/a(\d{6,})", re.I)

_STEALTH = Stealth(navigator_languages_override=("fr-FR", "fr"))


async def _apply_stealth(page, request):
    await page.add_init_script(_STEALTH.script_payload)


_PW_LISTING = {
    "playwright": True,
    "playwright_include_page": False,
    "playwright_page_init_callback": _apply_stealth,
    "playwright_page_goto_kwargs": {
        "wait_until": "domcontentloaded",
        "timeout": 60_000,
    },
}

# Les fiches produit Fnac chargent le prix via JS — on attend networkidle
_PW_PRODUCT = {
    "playwright": True,
    "playwright_include_page": False,
    "playwright_page_init_callback": _apply_stealth,
    "playwright_page_goto_kwargs": {
        "wait_until": "networkidle",
        "timeout": 60_000,
    },
}


class FnacSpider(BaseProductSpider):
    name = "fnac"
    merchant_slug = "fnac"
    allowed_domains = ["www.fnac.com"]

    start_urls = [
        "https://www.fnac.com/Ordinateurs-Portables/Informatique/n-10601/w-4",
        "https://www.fnac.com/Smartphone/Telephonie-Portable/n-10602/w-4",
        "https://www.fnac.com/TV-Video/TV/n-10607/w-4",
        "https://www.fnac.com/Son-et-Casques/Casques-et-Ecouteurs/n-10608/w-4",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 2.5,
        "DOWNLOAD_TIMEOUT": 60,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.5,
        # robots.txt de Fnac est protégé par DataDome (renvoie 429) —
        # les pages catalogue et produit sont publiquement accessibles.
        "ROBOTSTXT_OBEY": False,
    }

    # --- Sélecteurs fiche produit (fallback CSS) ---
    TITLE_SEL = (
        "h1.f-productHeader-Title::text, "
        "h1[itemprop='name']::text, "
        "h1::text"
    )
    PRICE_SELECTORS = (
        "span.userPrice span::text",
        "[itemprop='price']::attr(content)",
        "meta[itemprop='price']::attr(content)",
        "span.f-priceBox-price::text",
        "[class*='price'] strong::text",
        "[class*='Price'] span::text",
    )
    BRAND_SELECTORS = (
        "[itemprop='brand'] [itemprop='name']::attr(content)",
        "[itemprop='brand'] [itemprop='name']::text",
        "[itemprop='brand']::text",
        "a[class*='Brand']::text",
        "span[class*='brand']::text",
    )
    GTIN_SELECTORS = (
        "[itemprop='gtin13']::attr(content)",
        "[itemprop='gtin']::attr(content)",
        "meta[property='product:ean']::attr(content)",
    )
    STOCK_SELECTORS = (
        "[class*='availability']::text",
        "[class*='Availability']::text",
        "[class*='stock']::text",
        "[itemprop='availability']::attr(href)",
        "link[itemprop='availability']::attr(href)",
    )

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta=_PW_LISTING,
                callback=self.parse,
                errback=self.errback_log,
            )

    def extract_product_links(self, response) -> list[str]:
        hrefs = response.css("a::attr(href)").getall()
        return _dedupe_urls(
            response.urljoin(href)
            for href in hrefs
            if _SKU_RE.search(href)
        )

    def extract_next_page(self, response) -> str | None:
        href = response.css(
            "a[rel='next']::attr(href), "
            "a.next::attr(href), "
            "a[class*='next']::attr(href), "
            "a[class*='Next']::attr(href)"
        ).get()
        if href:
            return response.urljoin(href)

        for anchor in response.css("a"):
            label = " ".join(anchor.css("::text").getall()).strip().lower()
            if label in {"suivant", ">", "›", "page suivante"}:
                href = anchor.css("::attr(href)").get()
                if href:
                    return response.urljoin(href)
        return None

    def parse(self, response):
        links = self.extract_product_links(response)
        if not links:
            self.logger.warning(
                "Aucun lien produit extrait sur %s (status=%s, title=%r)",
                response.url,
                response.status,
                response.css("title::text").get(""),
            )

        for url in links:
            yield scrapy.Request(
                url,
                meta=_PW_PRODUCT,
                callback=self.parse_product,
                errback=self.errback_log,
            )

        next_page = self.extract_next_page(response)
        if next_page:
            yield scrapy.Request(
                next_page,
                meta=_PW_LISTING,
                callback=self.parse,
                errback=self.errback_log,
            )

    def parse_product(self, response):
        item = self._from_json_ld(response) or self._from_css(response)
        if item:
            yield self.dump_item(item, response)

    def errback_log(self, failure):
        request = failure.request
        self.logger.error("Erreur Fnac %s: %r", request.url, failure.value)

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

            sku = data.get("sku") or _sku_from_url(response.url)
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
            self.logger.warning("SKU Fnac introuvable : %s", response.url)
            return None

        title = _first_text(response.css(self.TITLE_SEL).getall())
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
