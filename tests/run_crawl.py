"""Crawl the local HTTPS target through the local CONNECT proxy."""

from __future__ import annotations

import json
import sys
from typing import Any

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.python import to_unicode

import scrapy_proxy_headers


class ProxyHeadersCompatSpider(scrapy.Spider):
    name = "proxy_headers_compat"

    def __init__(self, plan: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plan = plan
        self.results: list[dict[str, Any]] = []

    def _request(self, index: int) -> scrapy.Request:
        return scrapy.Request(
            f"{self.plan['target_base']}/?i={index}",
            meta={
                "proxy": self.plan["proxy"],
                "proxy_headers": {"X-ProxyMesh-Country": self.plan["steps"][index]},
                "_step": index,
            },
            callback=self.parse,
            errback=self.errback,
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
        self.results.append(
            {"index": index, "headers": headers, "target": json.loads(response.text)}
        )
        if index + 1 < len(self.plan["steps"]):
            yield self._request(index + 1)

    def errback(self, failure: Any) -> None:
        self.results.append(
            {
                "index": failure.request.meta.get("_step"),
                "error": failure.getErrorMessage(),
            }
        )


def _run(plan_path: str) -> int:
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
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
    crawler = process.create_crawler(ProxyHeadersCompatSpider)
    process.crawl(crawler, plan=plan)
    process.start()
    print(
        "RESULT "
        + json.dumps(
            {
                "mode": scrapy_proxy_headers.PROXY_HEADERS_MODE,
                "results": crawler.spider.results,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_run(sys.argv[1]))
