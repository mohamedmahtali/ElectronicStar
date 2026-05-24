"""Spider LDLC — électronique & informatique.

Stratégie :
  1. Parcourt les pages de catégorie (listing paginé) via Playwright (rendu JS)
  2. Sur chaque fiche produit, tente d'abord le JSON-LD schema.org/Product
  3. Repli sur sélecteurs CSS si le JSON-LD est absent ou incomplet
"""
import json
import re
from decimal import Decimal, InvalidOperation

import scrapy

from libs.crawling.schemas import RawItem

from .base import BaseProductSpider

_SKU_RE = re.compile(r"/(PB\d+)\.html", re.I)
_PRICE_DECIMAL_RE = re.compile(r"\d[\d\s\xa0\u202f.]*[.,]\d{2}")
_PRICE_EURO_RE = re.compile(
    r"(?P<euros>\d[\d\s\xa0\u202f.]*)\s*€\s*(?P<cents>\d{2})"
)

_PW_META = {
    "playwright": True,
    "playwright_include_page": False,
    "playwright_page_goto_kwargs": {
        "wait_until": "domcontentloaded",
        "timeout": 60000,
    },
}


class LdlcSpider(BaseProductSpider):
    name = "ldlc"
    merchant_slug = "ldlc"
    allowed_domains = ["www.ldlc.com"]

    start_urls = [
        "https://www.ldlc.com/informatique/ordinateur-portable/pc-portable/c4265/",
        "https://www.ldlc.com/telephonie/telephonie-portable/mobile-smartphone/c4416/",
        "https://www.ldlc.com/image-son/television/tv-ecran-plat/c4402/",
        "https://www.ldlc.com/image-son/son-numerique/casque/c4380/%2Bfc1456-1.html",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 2.0,
        "DOWNLOAD_TIMEOUT": 45,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    # --- Sélecteurs listing ---
    PRODUCT_LINK_SEL = "ul.listing-product li.pdt-item h3 a::attr(href)"
    NEXT_PAGE_SEL = "ul.pagination a.next::attr(href)"

    # --- Sélecteurs fiche produit (fallback CSS) ---
    TITLE_SEL = "h1::text"
    PRICE_SELECTORS = (
        "[itemprop='price']::attr(content)",
        "meta[property='product:price:amount']::attr(content)",
        "meta[property='product:price']::attr(content)",
        "div.price-box .price::text",
        "[class*='price']::text",
    )
    BRAND_SELECTORS = (
        ".manufacturer-infos a::text",
        "[itemprop='brand'] [itemprop='name']::attr(content)",
        "[itemprop='brand']::text",
        "meta[property='product:brand']::attr(content)",
    )
    GTIN_SELECTORS = (
        "meta[property='product:ean']::attr(content)",
        "[itemprop='gtin13']::attr(content)",
        "[itemprop='gtin']::attr(content)",
    )
    STOCK_SELECTORS = (
        ".stock-web .txt::text",
        "[class*='stock']::text",
        "[itemprop='availability']::attr(href)",
        "link[itemprop='availability']::attr(href)",
        "meta[property='product:availability']::attr(content)",
    )

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta=_PW_META,
                callback=self.parse,
                errback=self.errback_log,
            )

    def extract_product_links(self, response) -> list[str]:
        hrefs = response.css(f"{self.PRODUCT_LINK_SEL}, a::attr(href)").getall()
        return _dedupe_urls(
            response.urljoin(href)
            for href in hrefs
            if _SKU_RE.search(href)
        )

    def extract_next_page(self, response) -> str | None:
        href = response.css(
            f"{self.NEXT_PAGE_SEL}, a[rel='next']::attr(href), a.next::attr(href)"
        ).get()
        if href:
            return response.urljoin(href)

        for anchor in response.css("a"):
            label = " ".join(anchor.css("::text").getall()).strip().lower()
            if label in {"suivant", ">", "›"}:
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
                _first_text(response.css("title::text").getall()),
            )

        for url in links:
            yield scrapy.Request(
                url,
                meta=_PW_META,
                callback=self.parse_product,
                errback=self.errback_log,
            )

        next_page = self.extract_next_page(response)
        if next_page:
            yield scrapy.Request(
                next_page,
                meta=_PW_META,
                callback=self.parse,
                errback=self.errback_log,
            )

    def parse_product(self, response):
        item = self._from_json_ld(response) or self._from_css(response)
        if item:
            yield item.model_dump()

    def errback_log(self, failure):
        request = failure.request
        self.logger.error(
            "Erreur téléchargement LDLC %s: %r",
            request.url,
            failure.value,
        )

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
            self.logger.warning("SKU introuvable : %s", response.url)
            return None

        price_raw = _first_price_text(
            _flatten(response.css(selector).getall() for selector in self.PRICE_SELECTORS)
        )
        if not price_raw:
            price_raw = _first_price_text(response.css("body ::text").getall())
        price = _parse_price(price_raw)
        if price is None:
            self.logger.warning("Prix manquant sur %s", response.url)
            return None

        stock_text = _first_text(
            response.css(selector).getall() for selector in self.STOCK_SELECTORS
        ).lower()
        availability = _availability_from_text(
            stock_text or " ".join(response.css("body ::text").getall()).lower()
        )

        return RawItem(
            merchant_slug=self.merchant_slug,
            merchant_sku=sku,
            product_url=response.url,
            source_title=response.css(self.TITLE_SEL).get("").strip(),
            brand_raw=_first_text(
                response.css(selector).getall() for selector in self.BRAND_SELECTORS
            )
            or None,
            price_amount=price,
            availability=availability,
            gtin=_first_text(response.css(selector).getall() for selector in self.GTIN_SELECTORS) or None,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sku_from_url(url: str) -> str | None:
    m = _SKU_RE.search(url)
    return m.group(1) if m else None


def _parse_price(raw: str) -> Decimal | None:
    m = _PRICE_DECIMAL_RE.search(raw)
    if m:
        cleaned = _normalize_price_number(m.group())
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    m = _PRICE_EURO_RE.search(raw)
    if not m:
        return None

    euros = re.sub(r"[\s\xa0\u202f.]", "", m.group("euros"))
    try:
        return Decimal(f"{euros}.{m.group('cents')}")
    except InvalidOperation:
        return None


def _price_from_offers(offers) -> Decimal | None:
    if not offers:
        return None
    if isinstance(offers, list):
        if not offers:
            return None
        offers = offers[0]
    if not isinstance(offers, dict):
        return None

    for key in ("price", "lowPrice", "highPrice"):
        price = _parse_price(str(offers.get(key, "")))
        if price is not None:
            return price

    price_spec = offers.get("priceSpecification")
    if isinstance(price_spec, dict):
        return _parse_price(str(price_spec.get("price", "")))
    return None


def _brand_from_ld(data: dict) -> str | None:
    brand = data.get("brand")
    if isinstance(brand, dict):
        return brand.get("name") or None
    return brand or None


def _availability_from_offers(offers) -> str:
    if not offers:
        return "unknown"
    if isinstance(offers, list):
        if not offers:
            return "unknown"
        offers = offers[0]
    if not isinstance(offers, dict):
        return "unknown"
    avail = offers.get("availability", "")
    if "InStock" in avail:
        return "in_stock"
    if "OutOfStock" in avail:
        return "out_of_stock"
    return "unknown"


def _availability_from_text(text: str) -> str:
    if any(phrase in text for phrase in ("instock", "en stock", "dispo", "disponible")):
        return "in_stock"
    if any(
        phrase in text
        for phrase in ("outofstock", "rupture", "indisponible", "epuise", "épuisé")
    ):
        return "out_of_stock"
    return "unknown"


def _find_product_ld(data) -> dict | None:
    if isinstance(data, list):
        for item in data:
            product = _find_product_ld(item)
            if product is not None:
                return product
        return None

    if not isinstance(data, dict):
        return None

    types = data.get("@type")
    if types == "Product" or (isinstance(types, list) and "Product" in types):
        return data

    for key in ("@graph", "mainEntity", "itemListElement"):
        product = _find_product_ld(data.get(key))
        if product is not None:
            return product
    return None


def _dedupe_urls(urls) -> list[str]:
    seen = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _first_text(values) -> str:
    for value in _flatten(values):
        cleaned = " ".join(str(value).split()).strip()
        if cleaned:
            return cleaned
    return ""


def _flatten(values):
    for value in values:
        if isinstance(value, (list, tuple, set)):
            yield from _flatten(value)
        elif value is not None:
            yield value


def _first_price_text(texts) -> str:
    for text in texts:
        if _parse_price(text) is not None:
            return text

    joined = " ".join(str(text).strip() for text in texts if str(text).strip())
    matches = list(_iter_price_matches(joined))
    for match in matches:
        if not _is_secondary_price(joined, match.start(), match.end()):
            return match.group()
    return matches[0].group() if matches else ""


def _iter_price_matches(text: str):
    price_re = re.compile(
        r"\d[\d\s\xa0\u202f.]*€\s*\d{2}"
        r"|"
        r"\d[\d\s\xa0\u202f.]*[.,]\d{2}"
    )
    yield from price_re.finditer(text)


def _is_secondary_price(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 40):start].lower()
    after = text[end:end + 40].lower()

    if "mois" in after[:20] or "/mois" in after[:20]:
        return True
    if re.search(r"\b\d+\s*x\s*$", before):
        return True
    if "dont" in before[-12:] and "frais" in after[:25]:
        return True
    if "éco-part" in before[-30:] or "eco-part" in before[-30:]:
        return True
    if "reconditionn" in before:
        return True
    return False


def _normalize_price_number(raw: str) -> str:
    cleaned = raw.replace("\xa0", " ").replace("\u202f", " ").strip()
    cleaned = re.sub(r"\s", "", cleaned)
    if "," in cleaned:
        return cleaned.replace(".", "").replace(",", ".")
    if cleaned.count(".") == 1:
        return cleaned
    return cleaned.replace(".", "")
