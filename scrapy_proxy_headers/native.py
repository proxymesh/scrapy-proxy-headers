"""Capture CONNECT response headers on Scrapy 2.20 and newer.

Scrapy sends ``proxy_headers`` and discards the proxy response. A subclass of
``_TunnelProtocol`` keeps those headers. The factory looks the class up on the
module when a tunnel opens, so Scrapy still writes the CONNECT request.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from scrapy.core.downloader.handlers import http11
from scrapy.core.downloader.handlers.http11 import _TunnelProtocol
from scrapy.http import Headers, Response
from scrapy.utils._download_handlers import get_proxy_headers
from w3lib.url import add_http_if_no_scheme

from .connect import merge_proxy_response_headers, parse_connect_response_headers
from .download_handler import ProxyHeadersHandlerBase

logger = logging.getLogger(__name__)

_CAPTURED: dict[tuple[Any, ...], Headers] = {}
_installed = False


class _CapturingTunnelProtocol(_TunnelProtocol):
    """``_TunnelProtocol`` that keeps the CONNECT response headers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._captured = False

    def dataReceived(self, data: bytes) -> None:
        was_ready = self._tunnelReady
        super().dataReceived(data)
        if was_ready or self._captured or not self._tunnelReady:
            return
        header_block, separator, _rest = bytes(self._connectBuffer).partition(
            b"\r\n\r\n"
        )
        if not separator:
            return
        self._captured = True
        _CAPTURED[
            _request_key(self._proxyHost, self._proxyPort, self._proxyHeaders)
        ] = parse_connect_response_headers(header_block)


def sent_proxy_headers(request: Any) -> tuple[tuple[str, str], ...]:
    """Return the header tuple Scrapy passes to ``_TunnelProtocol``."""
    headers = tuple(get_proxy_headers(request))
    auth = request.headers.get(b"Proxy-Authorization")
    if auth and not any(name == "Proxy-Authorization" for name, _value in headers):
        text = auth.decode() if isinstance(auth, bytes) else str(auth)
        headers = (("Proxy-Authorization", text), *headers)
    return headers


def _request_key(host: Any, port: Any, headers: Any) -> tuple[Any, ...]:
    return (str(host).lower(), int(port), tuple(headers))


def _lookup(request: Any) -> Headers | None:
    proxy = request.meta.get("proxy")
    if not proxy:
        return None
    parsed = urlparse(add_http_if_no_scheme(proxy))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _CAPTURED.get(
        _request_key(parsed.hostname or "", port, sent_proxy_headers(request))
    )


class HTTP11ProxyDownloadHandler(ProxyHeadersHandlerBase):
    """Copy Scrapy's CONNECT response headers onto the download response."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        global _installed
        if not _installed:
            http11._TunnelProtocol = _CapturingTunnelProtocol
            _installed = True

    async def download_request(self, request: Any, spider: Any = None) -> Response:
        response = await super().download_request(request)
        captured = _lookup(request)
        if captured:
            merge_proxy_response_headers(response, captured)
        elif request.meta.get("proxy"):
            logger.warning(
                "No CONNECT response headers captured for %s", request.meta["proxy"]
            )
        return response
