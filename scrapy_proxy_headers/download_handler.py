"""HTTPS download handler that exposes proxy CONNECT response headers."""

from __future__ import annotations

import logging
from typing import Any

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Request, Response
from scrapy.utils.defer import maybe_deferred_to_future

from .connect import merge_proxy_response_headers, proxy_cache_key
from .mode import PROXY_HEADERS_MODE

logger = logging.getLogger(__name__)

if PROXY_HEADERS_MODE == "native":
    from .native import lookup_connect_response_headers
else:
    try:
        from .legacy import ScrapyProxyHeadersAgent
    except ImportError as exc:
        raise ImportError(
            "This Scrapy has neither native proxy_headers support nor the "
            "2.17–2.19 tunnel classes (_TunnelingTCP4ClientEndpoint)."
        ) from exc


class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
    """Merge CONNECT response headers into the Scrapy response.

    Configure it with::

        DOWNLOAD_HANDLERS = {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler",
        }

    ``request.meta["proxy_headers"]`` is sent on CONNECT. On Scrapy 2.20+
    Scrapy sends those headers and this handler only copies the proxy's
    response, including ``X-ProxyMesh-IP``. On Scrapy 2.17–2.19 this handler
    sends them. The cache key is the proxy URL plus the normalized headers,
    so two header sets do not share one ``X-ProxyMesh-IP``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy_response_headers_cache: dict[tuple[Any, ...], Any] = {}
        logger.info("scrapy-proxy-headers mode: %s", PROXY_HEADERS_MODE)

    async def download_request(self, request: Request, spider: Any = None) -> Response:
        """Download *request* and merge captured CONNECT headers onto it."""
        if PROXY_HEADERS_MODE == "native":
            response = await super().download_request(request)
            captured = lookup_connect_response_headers(request)
            return self._apply_cached_headers(response, request, captured)

        if spider is None:
            spider = self._crawler.spider
        agent = ScrapyProxyHeadersAgent(
            contextFactory=self._contextFactory,
            pool=self._pool,
            maxsize=getattr(spider, "download_maxsize", self._default_maxsize),
            warnsize=getattr(spider, "download_warnsize", self._default_warnsize),
            fail_on_dataloss=self._fail_on_dataloss,
            crawler=self._crawler,
            bindAddress=self._bind_address,
            tls_verbose_logging=self._tls_verbose_logging,
        )
        deferred = agent.download_request(request)
        deferred.addCallback(
            lambda response: self._apply_cached_headers(
                response, request, agent.proxy_response_headers
            )
        )
        return await maybe_deferred_to_future(deferred)

    def _apply_cached_headers(
        self,
        response: Response,
        request: Request,
        captured: Any,
    ) -> Response:
        proxy = request.meta.get("proxy")
        if not proxy or not isinstance(response, Response):
            return response
        key = proxy_cache_key(proxy, request.meta.get("proxy_headers"))
        if captured is not None:
            self._proxy_response_headers_cache[key] = captured
        cached = self._proxy_response_headers_cache.get(key)
        if cached:
            merge_proxy_response_headers(response, cached)
        elif PROXY_HEADERS_MODE == "native":
            logger.warning("No CONNECT response headers captured for proxy %s", proxy)
        return response
