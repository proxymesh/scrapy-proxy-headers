"""Compatibility tests that do not use a network proxy account."""

from __future__ import annotations

import doctest
import json
from pathlib import Path
from typing import Any

import pytest
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.http import Request
from scrapy.utils.python import to_unicode

from scrapy_proxy_headers.connect import (
    normalize_proxy_headers,
    parse_connect_response_headers,
    proxy_cache_key,
)
from tests.harness import (
    read_proxy_log,
    start_connect_proxy,
    start_https_target,
    write_self_signed_cert,
)

try:
    from scrapy.utils._download_handlers import get_proxy_headers

    from scrapy_proxy_headers.native import sent_proxy_headers
except ImportError:
    get_proxy_headers = None
    sent_proxy_headers = None

try:
    from scrapy_proxy_headers import legacy
except ImportError:
    legacy = None

native_only = pytest.mark.skipif(get_proxy_headers is None, reason="Scrapy 2.20+ only")
legacy_only = pytest.mark.skipif(legacy is None, reason="Scrapy 2.17-2.19 only")


@native_only
def test_native_sent_headers_match_scrapy() -> None:
    assert get_proxy_headers is not None and sent_proxy_headers is not None
    request = Request(
        "https://example.com/",
        headers={"Proxy-Authorization": "Basic dTpw"},
        meta={
            "proxy": "http://user:pass@proxy.example.com:31280",
            "proxy_headers": {"X-ProxyMesh-Country": "US"},
        },
    )
    sent = get_proxy_headers(request)
    assert sent_proxy_headers(request) == (("Proxy-Authorization", "Basic dTpw"), *sent)
    request.meta["proxy_headers"] = {
        "Proxy-Authorization": "from-meta",
        "X-ProxyMesh-Country": "US",
    }
    assert sent_proxy_headers(request) == get_proxy_headers(request)


def test_proxy_cache_key_includes_normalized_headers() -> None:
    us = proxy_cache_key("http://proxy.example.com:8080", {"X-ProxyMesh-Country": "US"})
    de = proxy_cache_key("http://proxy.example.com:8080", {"X-ProxyMesh-Country": "DE"})
    same = proxy_cache_key("proxy.example.com:8080", {"x-proxymesh-country": "US"})
    assert us != de
    assert us == same
    assert normalize_proxy_headers({"B": "2", "A": "1"}) == (("a", "1"), ("b", "2"))


def test_parse_connect_response_headers_skips_status_line() -> None:
    headers = parse_connect_response_headers(
        b"HTTP/1.1 200 Connection established\r\nX-Test-Proxy: 1\r\nX-Echo-Country: US\r\n"
    )
    assert headers.get("X-Test-Proxy") == b"1"
    assert headers.get("X-Echo-Country") == b"US"
    assert headers.get("HTTP/1.1 200 Connection established") is None


@legacy_only
def test_tunnel_request_doctest() -> None:
    assert legacy is not None
    result = doctest.testmod(legacy)
    assert result.failed == 0


class _CrawlSpider(scrapy.Spider):
    name = "proxy_headers_crawl"

    def __init__(self, plan: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plan = plan
        self.results: list[dict[str, Any]] = []

    def _request(self, index: int) -> scrapy.Request:
        return scrapy.Request(
            f"{self.plan['target']}/?i={index}",
            meta={
                "proxy": self.plan["proxy"],
                "proxy_headers": {"X-ProxyMesh-Country": self.plan["steps"][index]},
                "_step": index,
            },
            callback=self.parse,
            dont_filter=True,
        )

    async def start(self) -> Any:
        yield self._request(0)

    def parse(self, response: scrapy.http.Response) -> Any:
        index = response.meta["_step"]
        headers = {
            to_unicode(key).lower(): [to_unicode(value) for value in values]
            for key, values in response.headers.items()
        }
        self.results.append({"headers": headers, "target": json.loads(response.body)})
        if index + 1 < len(self.plan["steps"]):
            yield self._request(index + 1)


@pytest.fixture
def local_proxy(tmp_path: Path) -> Any:
    cert, key = write_self_signed_cert(tmp_path)
    log_path = tmp_path / "connect.log"
    target_port, stop_target = start_https_target(cert, key)
    proxy_port, stop_proxy = start_connect_proxy(log_path)
    try:
        yield {
            "proxy": f"http://127.0.0.1:{proxy_port}",
            "target": f"https://127.0.0.1:{target_port}",
            "log": log_path,
            "steps": ["US", "US", "DE", "US"],
        }
    finally:
        stop_proxy()
        stop_target()


def test_connect_headers_cache_and_reuse(local_proxy: dict[str, Any]) -> None:
    process = CrawlerProcess(
        settings={
            "LOG_LEVEL": "ERROR",
            "CONCURRENT_REQUESTS": 1,
            "RETRY_ENABLED": False,
            "DOWNLOAD_VERIFY_CERTIFICATES": False,
            "DOWNLOAD_HANDLERS": {
                "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
            },
        }
    )
    crawler = process.create_crawler(_CrawlSpider)
    process.crawl(crawler, plan=local_proxy)
    process.start()
    results = crawler.spider.results
    assert len(results) == 4
    events = [
        event
        for event in read_proxy_log(local_proxy["log"])
        if event["method"] == "CONNECT"
    ]

    def countries(event: dict[str, Any]) -> list[str]:
        return [
            str(pair[1])
            for pair in event["headers"]
            if str(pair[0]).lower() == "x-proxymesh-country"
        ]

    assert [countries(event) for event in events] == [["US"], ["DE"]]
    for event in events:
        names = [str(pair[0]).lower() for pair in event["headers"]]
        assert names.count("x-proxymesh-country") == 1
    for result, country in zip(results, local_proxy["steps"]):
        assert result["headers"]["x-test-proxy"] == ["1"]
        assert result["headers"]["x-echo-country"] == [country]
        assert not any(
            key.lower() == "x-proxymesh-country" for key in result["target"]["headers"]
        )
    assert sum(countries(event) == ["US"] for event in events) == 1
