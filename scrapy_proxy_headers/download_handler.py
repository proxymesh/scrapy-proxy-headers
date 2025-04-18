from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent

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
            # we need to do all this because the proxy tunnels can get re-used
            # when that happens, the proxy headers are not available in subsequent responses
            # so we need to save the proxy headers by the proxy, from the first tunnel response
            # so we can add them to subsequent responses
            def callback(response):
                if hasattr(response, '_proxy_response_headers'):
                    self._proxy_headers_by_proxy[proxy] = response._proxy_response_headers

                if proxy in self._proxy_headers_by_proxy:
                    response.headers.update(self._proxy_headers_by_proxy[proxy])

                return response

            response.addCallback(callback)
        return response