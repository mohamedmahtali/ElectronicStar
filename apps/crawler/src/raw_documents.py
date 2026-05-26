"""Helpers to capture raw crawl responses for later audit."""
from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from scrapy.http import Response


CAPTURED_HEADER_NAMES = {
    "cache-control",
    "content-language",
    "content-length",
    "content-type",
    "date",
    "etag",
    "last-modified",
    "server",
    "x-cache",
}


def raw_document_from_response(response: Response) -> dict:
    body = bytes(response.body or b"")
    return {
        "url": response.url,
        "doc_type": _doc_type(response),
        "http_status": int(response.status),
        "headers": _headers_to_json(response),
        "payload_sha256": hashlib.sha256(body).hexdigest(),
        "content_length": len(body),
        "body": body,
    }


def _doc_type(response: Response) -> str:
    content_type = response.headers.get(b"content-type", b"").decode(
        "latin1", errors="replace"
    )
    if "json" in content_type:
        return "json"
    if "html" in content_type:
        return "html"

    path = urlparse(response.url).path.lower()
    if path.endswith(".json"):
        return "json"
    return "html"


def _headers_to_json(response: Response) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, values in response.headers.items():
        name = key.decode("latin1", errors="replace").lower()
        if name not in CAPTURED_HEADER_NAMES:
            continue
        headers[name] = ", ".join(
            value.decode("latin1", errors="replace") for value in values
        )
    return headers
