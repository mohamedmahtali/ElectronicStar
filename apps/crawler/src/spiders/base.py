import scrapy
from scrapy import Spider


class BaseProductSpider(Spider):
    """Spider de base pour les marchands statiques.

    Sous-classes doivent implémenter `parse_product` et définir
    `merchant_slug`, `start_urls` et optionnellement `sitemap_urls`.
    """

    merchant_slug: str = ""

    custom_settings: dict = {
        "DOWNLOAD_DELAY": 1.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "ROBOTSTXT_OBEY": True,
    }

    def parse(self, response):
        """Détecte les liens produit sur une page catégorie et les suit."""
        for url in self.extract_product_links(response):
            yield scrapy.Request(url, callback=self.parse_product)

        next_page = self.extract_next_page(response)
        if next_page:
            yield scrapy.Request(next_page, callback=self.parse)

    def parse_product(self, response) -> dict:
        raise NotImplementedError

    def extract_product_links(self, response) -> list[str]:
        return []

    def extract_next_page(self, response) -> str | None:
        return None
