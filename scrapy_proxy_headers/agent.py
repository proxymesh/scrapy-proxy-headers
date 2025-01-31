# TODO: handle response headers

from scrapy.core.downloader.handlers.http11 import TunnelingAgent, TunnelingTCP4ClientEndpoint, ScrapyAgent, HTTP11DownloadHandler
from scrapy.core.downloader.webclient import _parse
from scrapy.utils.python import to_bytes

def tunnel_request_data_with_headers(host: str, port: int, **proxy_headers) -> bytes:
    r"""
    Return binary content of a CONNECT request.

    >>> from scrapy.utils.python import to_unicode as s
    >>> s(tunnel_request_data_with_headers("example.com", 8080))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\n\r\n'
    >>> s(tunnel_request_data_with_headers("example.com", 8080, **{"X-ProxyMesh-Country": "US"}))
    'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\nX-ProxyMesh-Country: US\r\n\r\n'
    >>> s(tunnel_request_data_with_headers(b"example.com", "8090"))
    'CONNECT example.com:8090 HTTP/1.1\r\nHost: example.com:8090\r\n\r\n'
    """
    host_value = to_bytes(host, encoding="ascii") + b":" + to_bytes(str(port))
    tunnel_req = b"CONNECT " + host_value + b" HTTP/1.1\r\n"
    tunnel_req += b"Host: " + host_value + b"\r\n"
    
    for key, val in proxy_headers.items():
        tunnel_req += to_bytes(key) + b": " + to_bytes(val) + b"\r\n"
    
    tunnel_req += b"\r\n"
    return tunnel_req

class TunnelingHeadersTCP4ClientEndpoint(TunnelingTCP4ClientEndpoint):
    def __init__(
        self,
        reactor,
        host: str,
        port: int,
        proxyConf,
        contextFactory,
        timeout: float = 30,
        bindAddress = None,
        **proxy_headers
    ):
        super().__init__(reactor, host, port, proxyConf, contextFactory, timeout, bindAddress)

        self._proxy_headers = {}
        if self._proxyAuthHeader:
            self._proxy_headers['Proxy-Authorization'] = self._proxyAuthHeader
        self._proxy_headers.update(proxy_headers)
    
    def requestTunnel(self, protocol):
        """Asks the proxy to open a tunnel."""
        assert protocol.transport
        tunnelReq = tunnel_request_data_with_headers(
            self._tunneledHost, self._tunneledPort, **self._proxy_headers
        )
        protocol.transport.write(tunnelReq)
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse  # type: ignore[method-assign]
        self._protocol = protocol
        return protocol

class TunnelingHeadersAgent(TunnelingAgent):
    """An agent that uses a L{TunnelingTCP4ClientEndpoint} to make HTTPS
    downloads. It may look strange that we have chosen to subclass Agent and not
    ProxyAgent but consider that after the tunnel is opened the proxy is
    transparent to the client; thus the agent should behave like there is no
    proxy involved.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy_headers = {}
    
    def set_proxy_headers(self, proxy_headers):
        self._proxy_headers = proxy_headers

    def _getEndpoint(self, uri):
        return TunnelingHeadersTCP4ClientEndpoint(
            reactor=self._reactor,
            host=uri.host,
            port=uri.port,
            proxyConf=self._proxyConf,
            contextFactory=self._contextFactory,
            timeout=self._endpointFactory._connectTimeout,
            bindAddress=self._endpointFactory._bindAddress,
            **self._proxy_headers
        )

class ScrapyProxyHeadersAgent(ScrapyAgent):
    _TunnelingAgent = TunnelingHeadersAgent
    
    def _get_agent(self, request, timeout: float):
        agent = super()._get_agent(request, timeout)

        proxy = request.meta.get("proxy")
        proxy_headers = request.meta.get('proxy_headers')
        if proxy and proxy_headers:
            scheme = _parse(request.url)[0]
            if scheme == b"https":
                agent.set_proxy_headers(proxy_headers)
        
        return agent

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