"""Detect whether this Scrapy sends ``proxy_headers`` itself."""

try:
    from scrapy.utils._download_handlers import get_proxy_headers as _get_proxy_headers
except ImportError:
    PROXY_HEADERS_MODE = "legacy"
else:
    PROXY_HEADERS_MODE = "native"
    del _get_proxy_headers
