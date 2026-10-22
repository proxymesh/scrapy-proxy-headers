"""Run one Scrapy crawl against the local CONNECT proxy.

The plan JSON has ``proxy``, ``target_base``, and ``steps`` (country codes).
Requests are chained so each download finishes before the next starts.
Prints a single ``RESULT`` JSON line.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import scrapy
from scrapy.crawler import CrawlerProcess

import scrapy_proxy_headers


def _header_lists(response: scrapy.http.Response) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for key, values in response.headers.items():
        name = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        decoded = [
            value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
            for value in values
        ]
        found.setdefault(name.lower(), []).extend(decoded)
    return found


class ProxyHeadersCompatSpider(scrapy.Spider):
    """Fetch the local HTTPS target through the local proxy."""

    name = "proxy_headers_compat"

    def __init__(self, plan: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plan = plan
        self.results: list[dict[str, Any]] = []

    async def start(self) -> Any:
        yield self._request(0)

    def _request(self, index: int) -> scrapy.Request:
        country = self.plan["steps"][index]
        return scrapy.Request(
            url=f"{self.plan['target_base']}/?i={index}",
            meta={
                "proxy": self.plan["proxy"],
                "proxy_headers": {"X-ProxyMesh-Country": country},
                "_step": index,
            },
            callback=self.parse,
            errback=self.errback,
            dont_filter=True,
        )

    def parse(self, response: scrapy.http.Response) -> Any:
        index = response.meta.get("_step")
        if index is None:
            query = response.url.split("i=", 1)[-1]
            index = int(query.split("&", 1)[0])
        headers = _header_lists(response)
        try:
            target = json.loads(response.text)
        except ValueError:
            target = {"raw": response.text}
        self.results.append(
            {
                "index": index,
                "url": response.url,
                "status": response.status,
                "headers": headers,
                "target": target,
            }
        )
        next_index = index + 1
        if next_index < len(self.plan["steps"]):
            yield self._request(next_index)

    def errback(self, failure: Any) -> None:
        request = getattr(failure, "request", None)
        index = None if request is None else request.meta.get("_step")
        self.results.append(
            {
                "index": index,
                "error": failure.getErrorMessage(),
                "traceback": failure.getTraceback(),
            }
        )


def _load_plan(argument: str) -> dict[str, Any]:
    if argument.endswith(".json"):
        with open(argument, encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(argument)


def _run(plan: dict[str, Any]) -> int:
    process = CrawlerProcess(
        settings={
            "LOG_ENABLED": True,
            "LOG_LEVEL": "DEBUG",
            "TELNETCONSOLE_ENABLED": False,
            "CONCURRENT_REQUESTS": 1,
            "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
            "DOWNLOAD_TIMEOUT": 30,
            "RETRY_ENABLED": False,
            "COOKIES_ENABLED": False,
            "REDIRECT_ENABLED": False,
            "DOWNLOAD_VERIFY_CERTIFICATES": False,
            "DOWNLOAD_HANDLERS": {
                "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler",
            },
        }
    )
    spider_holder: dict[str, ProxyHeadersCompatSpider] = {}

    def store(spider: ProxyHeadersCompatSpider) -> None:
        spider_holder["spider"] = spider

    crawler = process.create_crawler(ProxyHeadersCompatSpider)
    crawler.signals.connect(store, signal=scrapy.signals.spider_opened)
    process.crawl(crawler, plan=plan)
    process.start()
    spider = spider_holder.get("spider")
    payload = {
        "mode": scrapy_proxy_headers.PROXY_HEADERS_MODE,
        "detection": scrapy_proxy_headers.detection_details(),
        "results": [] if spider is None else spider.results,
    }
    print("RESULT " + json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_run(_load_plan(sys.argv[1])))
