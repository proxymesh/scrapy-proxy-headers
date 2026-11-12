"""Send proxy headers on HTTPS CONNECT and read the proxy's response headers."""

from .download_handler import HTTP11ProxyDownloadHandler
from .mode import PROXY_HEADERS_MODE

__all__ = [
    "PROXY_HEADERS_MODE",
    "HTTP11ProxyDownloadHandler",
]
