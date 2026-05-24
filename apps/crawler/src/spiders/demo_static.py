"""Spider de démonstration pour un site e-commerce statique générique.

À adapter par marchand réel : sélecteurs CSS, URL de départ, etc.
Respecte robots.txt par défaut (ROBOTSTXT_OBEY = True dans settings).
"""
import re
from decimal import Decimal, InvalidOperation

from libs.crawling.schemas import RawItem

from .base import BaseProductSpider


class DemoStaticSpider(BaseProductSpider):
    name = "demo_static"
    merchant_slug = "demo_marchand"
    allowed_domains: list[str] = []  # à renseigner par marchand réel
    start_urls: list[str] = []       # à renseigner par marchand réel

    # Sélecteurs CSS à adapter
    PRODUCT_LINK_SEL = "a.product-link::attr(href)"
    NEXT_PAGE_SEL = "a.pagination__next::attr(href)"
    TITLE_SEL = "h1.product-title::text"
    PRICE_SEL = "span.price::text"
    SKU_SEL = "meta[name='sku']::attr(content)"
    BRAND_SEL = "span.brand::text"
    AVAILABILITY_SEL = "span.availability::text"
    GTIN_SEL = "meta[itemprop='gtin13']::attr(content)"

    def extract_product_links(self, response) -> list[str]:
        return response.css(self.PRODUCT_LINK_SEL).getall()

    def extract_next_page(self, response) -> str | None:
        href = response.css(self.NEXT_PAGE_SEL).get()
        return response.urljoin(href) if href else None

    def parse_product(self, response) -> dict:
        title = (response.css(self.TITLE_SEL).get() or "").strip()
        price_raw = (response.css(self.PRICE_SEL).get() or "").strip()
        sku = (response.css(self.SKU_SEL).get() or "").strip()
        brand = (response.css(self.BRAND_SEL).get() or "").strip() or None
        availability = (response.css(self.AVAILABILITY_SEL).get() or "unknown").strip().lower()
        gtin = (response.css(self.GTIN_SEL).get() or "").strip() or None

        price = self._parse_price(price_raw)
        if price is None or not sku:
            self.logger.warning("Données manquantes sur %s", response.url)
            return {}

        item = RawItem(
            merchant_slug=self.merchant_slug,
            merchant_sku=sku,
            product_url=response.url,
            source_title=title,
            brand_raw=brand,
            price_amount=price,
            availability=availability,
            gtin=gtin,
        )
        return item.model_dump()

    @staticmethod
    def _parse_price(raw: str) -> Decimal | None:
        cleaned = re.sub(r"[^\d,.]", "", raw).replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
