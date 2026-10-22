"""HTTPS download handler that exposes proxy CONNECT response headers."""

from __future__ import annotations

import logging
from typing import Any

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Request, Response
from scrapy.utils.defer import maybe_deferred_to_future

from .compat import (
    NATIVE,
    PROXY_HEADERS_MODE,
    explain_capture_miss,
    legacy_classes,
    lookup_connect_response_headers,
)
from .connect import merge_proxy_response_headers, proxy_cache_key

logger = logging.getLogger(__name__)


class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
    """HTTPS handler that merges CONNECT response headers into the response.

    Public configuration is unchanged::

        DOWNLOAD_HANDLERS = {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler",
        }

    Send headers to the proxy with ``request.meta["proxy_headers"]``.
    Headers from the proxy's CONNECT response, such as ``X-ProxyMesh-IP``,
    are copied onto ``response.headers``.

    When :data:`~scrapy_proxy_headers.PROXY_HEADERS_MODE` is ``native``,
    Scrapy already sends ``proxy_headers``. This handler does not send them
    again. It records the CONNECT response by wrapping Scrapy's tunnel
    protocol and applies those headers, including after the tunnel is reused.

    When the mode is ``legacy`` (Scrapy 2.14.2 through 2.19.x), this handler
    sends ``proxy_headers`` on CONNECT itself.

    Cached CONNECT response headers are keyed by proxy URL and the normalized
    ``proxy_headers`` mapping, so two header sets for one proxy do not share
    a cached ``X-ProxyMesh-IP``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy_response_headers_cache: dict[tuple[Any, ...], Any] = {}
        logger.info(
            "scrapy-proxy-headers using %s Scrapy proxy_headers support",
            PROXY_HEADERS_MODE,
        )

    async def download_request(self, request: Request, spider: Any = None) -> Response:
        """Download *request* and merge CONNECT proxy headers into the response."""
        if PROXY_HEADERS_MODE == NATIVE:
            return await self._download_request_native(request)
        return await self._download_request_legacy(request, spider)

    async def _download_request_native(self, request: Request) -> Response:
        response = await super().download_request(request)
        captured = lookup_connect_response_headers(request)
        return self._apply_cached_headers(response, request, captured)

    async def _download_request_legacy(self, request: Request, spider: Any = None) -> Response:
        # Scrapy 2.14+ calls download_request(request). spider is accepted so
        # older engine call styles keep working.
        if spider is None:
            spider = self._crawler.spider

        agent_kwargs: dict[str, Any] = {
            "contextFactory": self._contextFactory,
            "pool": self._pool,
            "maxsize": getattr(spider, "download_maxsize", self._default_maxsize),
            "warnsize": getattr(spider, "download_warnsize", self._default_warnsize),
            "fail_on_dataloss": self._fail_on_dataloss,
            "crawler": self._crawler,
        }
        bind_address = getattr(self, "_bind_address", None)
        if bind_address is not None:
            agent_kwargs["bindAddress"] = bind_address
        tls_verbose = getattr(self, "_tls_verbose_logging", None)
        if tls_verbose is not None:
            agent_kwargs["tls_verbose_logging"] = tls_verbose

        agent_cls = legacy_classes()["ScrapyProxyHeadersAgent"]
        agent = agent_cls(**agent_kwargs)
        deferred = agent.download_request(request)

        def callback(response: Response) -> Response:
            return self._apply_cached_headers(response, request, agent.proxy_response_headers)

        deferred.addCallback(callback)
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
        elif PROXY_HEADERS_MODE == NATIVE:
            logger.warning(
                "No CONNECT response headers captured for proxy %s with "
                "proxy_headers %r. %s",
                proxy,
                request.meta.get("proxy_headers"),
                explain_capture_miss(request),
            )
        return response
