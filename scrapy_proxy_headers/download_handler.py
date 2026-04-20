from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.http import Headers
from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent

PROXY_HEADER_PREFIXES = (b'x-proxymesh-', b'proxy-')

class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy_headers_by_proxy = {}
    
    def download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        agent = ScrapyProxyHeadersAgent(
            contextFactory=self._contextFactory,
            pool=self._pool,
            maxsize=getattr(spider, "download_maxsize", self._default_maxsize),
            warnsize=getattr(spider, "download_warnsize", self._default_warnsize),
            fail_on_dataloss=self._fail_on_dataloss,
            crawler=self._crawler,
        )
        response = agent.download_request(request)
        proxy = request.meta.get("proxy")

        if proxy:
            def callback(response):
                proxy_headers = self._extract_proxy_headers(response.headers)
                if proxy_headers:
                    self._proxy_headers_by_proxy[proxy] = proxy_headers

                if proxy in self._proxy_headers_by_proxy:
                    response.headers.update(self._proxy_headers_by_proxy[proxy])

                return response

            response.addCallback(callback)
        return response
    
    def _extract_proxy_headers(self, headers):
        """Extract proxy-related headers from response headers."""
        proxy_headers = Headers()
        for key in headers.keys():
            key_lower = key.lower()
            if any(key_lower.startswith(prefix) for prefix in PROXY_HEADER_PREFIXES):
                proxy_headers[key] = headers.getlist(key)
        return proxy_headers if proxy_headers.keys() else None