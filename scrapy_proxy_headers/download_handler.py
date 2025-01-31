from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent

class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
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
        return agent.download_request(request)