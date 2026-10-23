"""Backwards-compatible access to the legacy tunnel helpers.

Private Scrapy symbols are resolved in :mod:`scrapy_proxy_headers.compat`.
On Scrapy with native ``proxy_headers`` support the legacy endpoint classes
are not defined; import :class:`~scrapy_proxy_headers.HTTP11ProxyDownloadHandler`
instead.
"""

from __future__ import annotations

from typing import Any

from .compat import (
    LEGACY,
    PROXY_HEADERS_MODE,
    ScrapyInternalsError,
    legacy_classes,
)
from .connect import tunnel_request_data_with_headers

__all__ = [
    "PROXY_HEADERS_MODE",
    "ScrapyInternalsError",
    "ScrapyProxyHeadersAgent",
    "TunnelingHeadersAgent",
    "TunnelingHeadersTCP4ClientEndpoint",
    "tunnel_request_data_with_headers",
]

if PROXY_HEADERS_MODE == LEGACY:
    _legacy = legacy_classes()
    TunnelingHeadersTCP4ClientEndpoint = _legacy["TunnelingHeadersTCP4ClientEndpoint"]
    TunnelingHeadersAgent = _legacy["TunnelingHeadersAgent"]
    ScrapyProxyHeadersAgent = _legacy["ScrapyProxyHeadersAgent"]


def __getattr__(name: str) -> Any:
    if name in {
        "TunnelingHeadersTCP4ClientEndpoint",
        "TunnelingHeadersAgent",
        "ScrapyProxyHeadersAgent",
    }:
        raise ScrapyInternalsError(
            f"{name} belongs to the legacy Scrapy tunnel path. This interpreter "
            f"is in {PROXY_HEADERS_MODE!r} mode, where Scrapy sends proxy_headers "
            "itself. Use scrapy_proxy_headers.HTTP11ProxyDownloadHandler to "
            "capture CONNECT response headers."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
