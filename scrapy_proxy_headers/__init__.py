"""Send proxy headers on HTTPS CONNECT and read the proxy's response headers."""

from .download_handler import HTTP11ProxyDownloadHandler
from .mode import PROXY_HEADERS_MODE

__all__ = [
    "HTTP11ProxyDownloadHandler",
    "PROXY_HEADERS_MODE",
]
