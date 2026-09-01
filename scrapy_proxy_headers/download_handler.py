from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent


class HTTP11ProxyDownloadHandler(HTTP11DownloadHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy_headers_by_proxy = {}

    async def download_request(self, request, spider=None):
        """Download the request and merge CONNECT proxy headers into the response."""
        # Support both old Scrapy (spider param) and new Scrapy (self._crawler.spider)
        if spider is None:
            spider = self._crawler.spider

        agent_kwargs = {
            "contextFactory": self._contextFactory,
            "pool": self._pool,
            "maxsize": getattr(spider, "download_maxsize", self._default_maxsize),
            "warnsize": getattr(spider, "download_warnsize", self._default_warnsize),
            "fail_on_dataloss": self._fail_on_dataloss,
            "crawler": self._crawler,
        }
        bind_address = getattr(self, "_bind_address", None)
        if bind_address is not None:
            agent_kwargs["bindAddress"] = bind_address

        agent = ScrapyProxyHeadersAgent(**agent_kwargs)
        deferred = agent.download_request(request)
        proxy = request.meta.get("proxy")

        if proxy:
            # Proxy tunnels can get re-used; when that happens, proxy headers
            # are not available in subsequent responses. Save proxy headers by
            # proxy URL from the first tunnel response to add to later responses.
            def callback(response):
                if agent.proxy_response_headers:
                    self._proxy_headers_by_proxy[proxy] = agent.proxy_response_headers

                if proxy in self._proxy_headers_by_proxy:
                    response.headers.update(self._proxy_headers_by_proxy[proxy])

                return response

            deferred.addCallback(callback)
        return await maybe_deferred_to_future(deferred)
