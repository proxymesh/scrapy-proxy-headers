"""Send proxy headers on HTTPS CONNECT and read the proxy's response headers."""

from .compat import (
    PROXY_HEADERS_MODE,
    ScrapyInternalsError,
    detection_details,
    get_proxy_headers_mode,
)
from .download_handler import HTTP11ProxyDownloadHandler

__all__ = [
    "HTTP11ProxyDownloadHandler",
    "PROXY_HEADERS_MODE",
    "ScrapyInternalsError",
    "detection_details",
    "get_proxy_headers_mode",
]
