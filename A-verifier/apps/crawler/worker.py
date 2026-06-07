"""Point d'entrée du worker crawler : python -m apps.crawler.worker --spider <name>"""
import argparse

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spider", required=True, help="Nom du spider à lancer")
    args = parser.parse_args()

    settings = get_project_settings()
    process = CrawlerProcess(settings)
    process.crawl(args.spider)
    process.start()


if __name__ == "__main__":
    main()
