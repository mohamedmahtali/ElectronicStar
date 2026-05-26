"""Spider Materiel.net — informatique & high-tech.

Le site expose assez peu de JSON-LD utile dans le HTML rendu, donc ce spider
s'appuie surtout sur le texte visible de la fiche produit et sur quelques
sélecteurs CSS stables.
"""
import re

import scrapy

from libs.crawling.schemas import RawItem

from .base import BaseProductSpider
from .ldlc import _availability_from_text, _dedupe_urls, _parse_price

_SKU_RE = re.compile(r"/produit/(\d+)\.html", re.I)
_PRICE_RE = re.compile(
    r"\d[\d\s\xa0\u202f.]*€\s*\d{2}"
    r"|"
    r"\d[\d\s\xa0\u202f.]*[.,]\d{2}"
)
_PW_META = {
    "playwright": True,
    "playwright_include_page": False,
    "playwright_page_goto_kwargs": {
        "wait_until": "domcontentloaded",
        "timeout": 60000,
    },
}


class MaterielSpider(BaseProductSpider):
    name = "materiel"
    merchant_slug = "materiel"
    allowed_domains = ["www.materiel.net", "materiel.net"]

    start_urls = [
        "https://www.materiel.net/pc-portable/l409/",
        "https://www.materiel.net/casque-audio/l575/",
        "https://www.materiel.net/television/c552/",
    ]

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "DOWNLOAD_DELAY": 2.0,
        "DOWNLOAD_TIMEOUT": 45,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta=_PW_META,
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
        href = response.css("a[rel='next']::attr(href), a.next::attr(href)").get()
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
                "Aucun lien produit extrait sur %s (status=%s)",
                response.url,
                response.status,
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
        item = self._from_css(response)
        if item:
            yield self.dump_item(item, response)

    def errback_log(self, failure):
        request = failure.request
        self.logger.error("Erreur téléchargement Materiel.net %s: %r", request.url, failure.value)

    def _from_css(self, response) -> RawItem | None:
        sku = _sku_from_url(response.url)
        if not sku:
            self.logger.warning("SKU introuvable : %s", response.url)
            return None

        texts = response.css("body ::text").getall()
        title = " ".join(response.css("h1::text").getall()).strip()
        if not title:
            self.logger.warning("Titre manquant sur %s", response.url)
            return None

        price_text = _first_product_price_text(texts)
        price = _parse_price(price_text)
        if price is None:
            self.logger.warning("Prix manquant sur %s", response.url)
            return None

        joined_text = " ".join(texts).lower()

        return RawItem(
            merchant_slug=self.merchant_slug,
            merchant_sku=sku,
            product_url=response.url,
            source_title=title,
            brand_raw=_value_after_label(texts, "Marque") or _brand_from_title(title),
            price_amount=price,
            availability=_availability_from_text(joined_text),
            gtin=(
                _value_after_label(texts, "Code EAN")
                or _value_after_label(texts, "EAN")
                or None
            ),
            mpn=_value_after_label(texts, "Modèle") or None,
        )


def _sku_from_url(url: str) -> str | None:
    match = _SKU_RE.search(url)
    return match.group(1) if match else None


def _first_product_price_text(texts) -> str:
    cleaned = [" ".join(str(text).split()).strip() for text in texts if str(text).strip()]
    joined = " ".join(cleaned)
    for match in _PRICE_RE.finditer(joined):
        if not _is_secondary_product_price(joined, match.start(), match.end()):
            return match.group()
    return ""


def _is_secondary_product_price(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 80):start].lower()
    after = text[end:end + 80].lower()

    if start > 0 and text[start - 1] == "/":
        return True
    if "prix le + bas" in after[:60] or "prix le plus bas" in after[:60]:
        return True
    for phrase in ("prix le + bas", "prix le plus bas"):
        position = before.rfind(phrase)
        if position >= 0 and not _PRICE_RE.search(before[:position][-50:]):
            return True
    if any(phrase in before[-80:] for phrase in ("à partir de", "a partir de", "destockage")):
        return True
    if any(phrase in after[:40] for phrase in ("/mois", "mois")):
        return True
    if re.search(r"\b\d+\s*x\s*$", before):
        return True
    if any(
        phrase in before[-50:]
        for phrase in ("éco-participation", "eco-participation", "éco-part.", "eco-part.")
    ):
        return True
    return False


def _value_after_label(texts, label: str) -> str:
    normalized_label = label.strip().casefold()
    cleaned = [" ".join(str(text).split()).strip() for text in texts if str(text).strip()]

    for index, text in enumerate(cleaned):
        if text.casefold() != normalized_label:
            continue
        for value in cleaned[index + 1:index + 6]:
            if value.casefold() != normalized_label:
                return value
    return ""


def _brand_from_title(title: str) -> str | None:
    first_word = title.split(maxsplit=1)[0].strip()
    return first_word or None
