"""
To use this, in your settings, do the following:

DOWNLOAD_HANDLERS = {
  "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
}

Then when you make a request with a custom proxy header, instead of using request.headers, use request.meta["proxy_headers"] like this:

request.meta["proxy_headers"] = {"X-ProxyMesh-Country": "US"}
"""

from .download_handler import HTTP11ProxyDownloadHandler