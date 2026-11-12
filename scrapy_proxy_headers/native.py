"""Capture CONNECT response headers on Scrapy 2.20 and newer.

Scrapy sends ``request.meta["proxy_headers"]`` and then discards the proxy's
CONNECT response. Replacing ``http11._TunnelProtocol`` records those headers.
``_TunnelFactory.buildProtocol`` looks the class up on the module when it
runs, so Scrapy's own ``connectionMade`` still writes the CONNECT request.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import scrapy.core.downloader.handlers.http11 as http11
from scrapy.core.downloader.handlers.http11 import _TunnelProtocol
from scrapy.http import Headers
from scrapy.utils._download_handlers import get_proxy_headers
from scrapy.utils.url import add_http_if_no_scheme

from .connect import parse_connect_response_headers

_CAPTURED: dict[tuple[Any, ...], Headers] = {}


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
        header_block, separator, _rest = bytes(self._connectBuffer).partition(b"\r\n\r\n")
        if not separator:
            return
        self._captured = True
        headers = parse_connect_response_headers(header_block)
        _CAPTURED[_capture_key(self._proxyHost, self._proxyPort, self._proxyHeaders)] = headers


http11._TunnelProtocol = _CapturingTunnelProtocol


def sent_proxy_headers(request: Any) -> tuple[tuple[str, str], ...]:
    """Return the header tuple Scrapy passes to ``_TunnelProtocol``.

    ``proxy_headers`` wins when it already contains ``Proxy-Authorization``.
    """
    headers = tuple(get_proxy_headers(request))
    auth = request.headers.get(b"Proxy-Authorization")
    if auth and not any(name == "Proxy-Authorization" for name, _value in headers):
        text = auth.decode() if isinstance(auth, bytes) else str(auth)
        headers = (("Proxy-Authorization", text), *headers)
    return headers


def lookup_connect_response_headers(request: Any) -> Headers | None:
    """Return CONNECT response headers captured for *request*, if any."""
    proxy = request.meta.get("proxy")
    if not proxy:
        return None
    parsed = urlparse(add_http_if_no_scheme(proxy))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    key = _capture_key(parsed.hostname or "", port, sent_proxy_headers(request))
    return _CAPTURED.get(key)


def _capture_key(host: Any, port: Any, headers: Any) -> tuple[Any, ...]:
    return (str(host).lower(), int(port), tuple(headers))
