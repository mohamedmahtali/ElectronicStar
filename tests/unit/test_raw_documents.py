import hashlib

from scrapy.http import HtmlResponse

from apps.crawler.src.raw_documents import raw_document_from_response


def test_raw_document_from_response_captures_auditable_metadata():
    body = b"<html><body>499,95</body></html>"
    response = HtmlResponse(
        url="https://www.ldlc.com/fiche/PB00728588.html",
        status=200,
        body=body,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "ETag": '"abc"',
            "Set-Cookie": "ignored=true",
        },
    )

    document = raw_document_from_response(response)

    assert document["url"] == "https://www.ldlc.com/fiche/PB00728588.html"
    assert document["doc_type"] == "html"
    assert document["http_status"] == 200
    assert document["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert document["content_length"] == len(body)
    assert document["body"] == body
    assert document["headers"] == {
        "content-type": "text/html; charset=utf-8",
        "etag": '"abc"',
    }
