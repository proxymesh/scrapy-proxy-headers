from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent


class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy_headers_by_proxy = {}
    
    def download_request(self, request, spider=None):
        """Return a deferred for the HTTP download"""
        # Support both old Scrapy (spider param) and new Scrapy (self._crawler.spider)
        if spider is None:
            spider = self._crawler.spider
        
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
                if agent.proxy_response_headers:
                    self._proxy_headers_by_proxy[proxy] = agent.proxy_response_headers

                if proxy in self._proxy_headers_by_proxy:
                    response.headers.update(self._proxy_headers_by_proxy[proxy])

                return response

            response.addCallback(callback)
        return response