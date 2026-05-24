PRODUCTS_INDEX_WRITE = "products-write-v1"
PRODUCTS_INDEX_READ_ALIAS = "products-read"

PRODUCTS_TEMPLATE: dict = {
    "index_patterns": ["products-write-v*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "french_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "french_stop", "french_stemmer"],
                    }
                },
                "filter": {
                    "french_stop": {"type": "stop", "stopwords": "_french_"},
                    "french_stemmer": {"type": "stemmer", "language": "light_french"},
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "product_id": {"type": "keyword"},
                "canonical_key": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "french_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "brand": {"type": "keyword"},
                "category_path": {"type": "keyword"},
                "gtin": {"type": "keyword"},
                "mpn": {"type": "keyword"},
                "specs": {"type": "flattened"},
                "price_min": {"type": "float"},
                "price_max": {"type": "float"},
                "merchant_ids": {"type": "keyword"},
                "offers": {
                    "type": "nested",
                    "properties": {
                        "merchant_id": {"type": "keyword"},
                        "merchant_name": {"type": "keyword"},
                        "price_amount": {"type": "float"},
                        "shipping_amount": {"type": "float"},
                        "availability": {"type": "keyword"},
                        "condition": {"type": "keyword"},
                        "product_url": {"type": "keyword", "index": False},
                        "last_seen_at": {"type": "date"},
                    },
                },
                "updated_at": {"type": "date"},
            },
        },
        "aliases": {PRODUCTS_INDEX_READ_ALIAS: {}},
    },
}

CRAWL_LOGS_TEMPLATE: dict = {
    "index_patterns": ["crawl-logs-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "merchant": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "message": {"type": "text"},
                "url": {"type": "keyword"},
                "status": {"type": "integer"},
                "duration_ms": {"type": "long"},
                "timestamp": {"type": "date"},
            }
        },
    },
}
