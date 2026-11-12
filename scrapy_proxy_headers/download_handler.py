"""Shared cache for proxy CONNECT response headers."""

from __future__ import annotations

from typing import Any

from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Request, Response

from .connect import merge_proxy_response_headers, proxy_cache_key


class ProxyHeadersHandlerBase(HTTP11DownloadHandler):
    """Cache CONNECT response headers by proxy URL and ``proxy_headers``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy_response_headers_cache: dict[tuple[Any, ...], Any] = {}

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
        return response
