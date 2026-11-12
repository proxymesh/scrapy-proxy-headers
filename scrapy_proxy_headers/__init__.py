"""Send proxy headers on HTTPS CONNECT and read the proxy's response headers."""

try:
    from .native import HTTP11ProxyDownloadHandler
except ImportError:
    from .legacy import HTTP11ProxyDownloadHandler

__all__ = ["HTTP11ProxyDownloadHandler"]
