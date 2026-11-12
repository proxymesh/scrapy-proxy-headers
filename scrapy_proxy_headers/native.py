"""Capture CONNECT response headers on Scrapy 2.20 and newer.

Scrapy sends ``proxy_headers`` and discards the proxy response. A subclass of
``_TunnelProtocol`` keeps those headers. The factory looks the class up on the
module when a tunnel opens, so Scrapy still writes the CONNECT request.
"""

from __future__ import annotations

import logging
import weakref
from typing import Any
from urllib.parse import urlparse

from scrapy.core.downloader.handlers import http11
from scrapy.core.downloader.handlers.http11 import _TunnelProtocol
from scrapy.http import Headers, Response
from scrapy.utils._download_handlers import get_proxy_headers
from scrapy.utils.httpobj import urlparse_cached
from w3lib.url import add_http_if_no_scheme

from .connect import parse_connect_response_headers, proxy_cache_key
from .download_handler import ProxyHeadersHandlerBase

logger = logging.getLogger(__name__)

_handler: HTTP11ProxyDownloadHandler | None = None
_installed = False


class _CapturingTunnelProtocol(_TunnelProtocol):
    """``_TunnelProtocol`` that keeps the CONNECT response headers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._response_headers: Headers | None = None
        if _handler is not None:
            _handler._tunnels.add(self)

    def dataReceived(self, data: bytes) -> None:
        was_ready = self._tunnelReady
        super().dataReceived(data)
        if was_ready or self._response_headers is not None or not self._tunnelReady:
            return
        header_block, separator, _rest = bytes(self._connectBuffer).partition(
            b"\r\n\r\n"
        )
        if separator:
            self._response_headers = parse_connect_response_headers(header_block)


def sent_proxy_headers(request: Any) -> tuple[tuple[str, str], ...]:
    """Return the header tuple Scrapy passes to ``_TunnelProtocol``."""
    headers = tuple(get_proxy_headers(request))
    auth = request.headers.get(b"Proxy-Authorization")
    if auth and not any(name == "Proxy-Authorization" for name, _value in headers):
        text = auth.decode() if isinstance(auth, bytes) else str(auth)
        headers = (("Proxy-Authorization", text), *headers)
    return headers


class HTTP11ProxyDownloadHandler(ProxyHeadersHandlerBase):
    """Copy Scrapy's CONNECT response headers onto the download response."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tunnels: weakref.WeakSet[_CapturingTunnelProtocol] = weakref.WeakSet()
        global _handler, _installed
        _handler = self
        if not _installed:
            http11._TunnelProtocol = _CapturingTunnelProtocol
            _installed = True

    def _connect_headers(self, request: Any) -> Headers | None:
        proxy = request.meta.get("proxy")
        if not proxy:
            return None
        parsed = urlparse(add_http_if_no_scheme(proxy))
        host = (parsed.hostname or "").lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        sent = sent_proxy_headers(request)
        for protocol in self._tunnels:
            if protocol._response_headers is None:
                continue
            if (
                str(protocol._proxyHost).lower() == host
                and int(protocol._proxyPort) == port
                and tuple(protocol._proxyHeaders) == sent
            ):
                return protocol._response_headers
        return None

    async def download_request(self, request: Any) -> Response:
        response = await super().download_request(request)
        response = self._apply_cached_headers(
            response, request, self._connect_headers(request)
        )
        proxy = request.meta.get("proxy")
        if (
            proxy
            and urlparse_cached(request).scheme == "https"
            and proxy_cache_key(proxy, request.meta.get("proxy_headers"))
            not in self._proxy_response_headers_cache
        ):
            logger.warning("No CONNECT response headers captured for %s", proxy)
        return response
