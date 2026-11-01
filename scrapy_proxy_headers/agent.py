from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from scrapy import Request
from scrapy.core.downloader.handlers import http11 as _http11
from scrapy.http import Headers, Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import to_bytes
from scrapy.utils.url import add_http_if_no_scheme

# CONNECT metadata must never impersonate origin HTTP semantics.
_FORBIDDEN_CONNECT_HEADER_NAMES = frozenset(
    name.encode("ascii")
    for name in (
        "set-cookie",
        "set-cookie2",
        "cookie",
        "content-type",
        "content-length",
        "content-encoding",
        "content-language",
        "content-location",
        "content-disposition",
        "content-range",
        "location",
        "refresh",
        "www-authenticate",
        "authorization",
        "proxy-authenticate",
        "proxy-authorization",
        "cache-control",
        "expires",
        "etag",
        "last-modified",
        "age",
        "vary",
        "pragma",
        "date",
        "referer",
        "referrer-policy",
        "strict-transport-security",
        "content-security-policy",
        "content-security-policy-report-only",
        "x-frame-options",
        "x-content-type-options",
        "x-xss-protection",
        "access-control-allow-origin",
        "access-control-allow-credentials",
        "access-control-allow-headers",
        "access-control-allow-methods",
        "access-control-expose-headers",
        "access-control-max-age",
        "link",
        "alt-svc",
        "clear-site-data",
        "permissions-policy",
        "host",
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "server",
    )
)


def _contains_ctl_or_newline(raw: bytes) -> bool:
    return b"\r" in raw or b"\n" in raw or b"\x00" in raw


def _header_name_bytes(name: Any) -> bytes:
    """Return a CONNECT header name, rejecting CR/LF/NUL, spaces, and colons."""
    raw = to_bytes(name)
    if not raw or _contains_ctl_or_newline(raw) or b":" in raw or b" " in raw or b"\t" in raw:
        raise ValueError("Invalid CONNECT header name")
    return raw


def _header_value_bytes(value: Any) -> bytes:
    """Return a CONNECT header value, rejecting CR/LF/NUL."""
    raw = to_bytes(value)
    if _contains_ctl_or_newline(raw):
        raise ValueError("Invalid CONNECT header value")
    return raw


def parse_connect_response_headers(data: bytes) -> Headers:
    """Parse headers from a CONNECT response, stopping at the header terminator.

    Bytes after the first ``\\r\\n\\r\\n`` are ignored so TLS or body data cannot
    be interpreted as headers.
    """
    header_block = data.split(b"\r\n\r\n", 1)[0]
    parsed = {}
    for line in header_block.split(b"\r\n"):
        if b":" not in line:
            continue
        name, value = line.split(b":", 1)
        name = name.strip()
        value = value.strip()
        if not name or b" " in name or _contains_ctl_or_newline(name):
            continue
        if _contains_ctl_or_newline(value):
            continue
        parsed[name] = value
    return Headers(parsed)


def _is_forbidden_connect_header(name: Any) -> bool:
    return to_bytes(name).lower() in _FORBIDDEN_CONNECT_HEADER_NAMES


def merge_proxy_response_headers(
    response: Response,
    proxy_headers: Headers,
    request: Optional[Request] = None,
) -> None:
    """Expose CONNECT headers without letting them impersonate the origin.

    All parsed CONNECT headers are stored on
    ``request.meta['proxy_response_headers']`` (and therefore
    ``response.meta`` once the engine attaches the request). Only headers
    that are not origin-semantic and not already present on the HTTPS
    response are copied into ``response.headers``, so values such as
    ``X-ProxyMesh-IP`` remain available to spiders.
    """
    stored = Headers(proxy_headers)
    meta_owner = request if request is not None else getattr(response, "request", None)
    if meta_owner is not None:
        meta_owner.meta["proxy_response_headers"] = stored
    for name in stored.keys():
        if _is_forbidden_connect_header(name):
            continue
        if name in response.headers:
            continue
        response.headers.setlist(name, stored.getlist(name))

# Scrapy 2.18 made these HTTP11 internals private (leading underscore).
TunnelingTCP4ClientEndpoint = getattr(
    _http11, "TunnelingTCP4ClientEndpoint", None
) or getattr(_http11, "_TunnelingTCP4ClientEndpoint")
TunnelingAgent = getattr(_http11, "TunnelingAgent", None) or getattr(
    _http11, "_TunnelingAgent"
)
ScrapyAgent = getattr(_http11, "ScrapyAgent", None) or getattr(_http11, "_ScrapyAgent")


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
    host_b = to_bytes(host, encoding="ascii")
    port_b = to_bytes(str(port), encoding="ascii")
    if not host_b or _contains_ctl_or_newline(host_b) or b" " in host_b:
        raise ValueError("Invalid CONNECT host")
    if not port_b or _contains_ctl_or_newline(port_b) or b" " in port_b:
        raise ValueError("Invalid CONNECT port")
    host_value = host_b + b":" + port_b
    tunnel_req = b"CONNECT " + host_value + b" HTTP/1.1\r\n"
    tunnel_req += b"Host: " + host_value + b"\r\n"

    for key, val in proxy_headers.items():
        tunnel_req += _header_name_bytes(key) + b": " + _header_value_bytes(val) + b"\r\n"

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
        bindAddress=None,
        proxy_headers: Optional[Mapping[Any, Any]] = None,
    ):
        super().__init__(reactor, host, port, proxyConf, contextFactory, timeout, bindAddress)

        self._proxy_headers = {}
        if self._proxyAuthHeader:
            self._proxy_headers["Proxy-Authorization"] = self._proxyAuthHeader
        if proxy_headers:
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

    def processProxyResponse(self, data: bytes):
        """Parse CONNECT headers from the reassembled buffer, not this chunk.

        The parent endpoint buffers TCP chunks until ``\\r\\n\\r\\n``. Parsing
        only ``data`` drops header lines from earlier chunks and can treat
        bytes after a split terminator as headers.
        """
        result = super(TunnelingHeadersTCP4ClientEndpoint, self).processProxyResponse(data)
        if b"\r\n\r\n" in self._connectBuffer:
            self._proxy_response_headers = parse_connect_response_headers(
                bytes(self._connectBuffer)
            )
        return result


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

    def set_proxy_headers(self, proxy_headers: Mapping[Any, Any]) -> None:
        self._proxy_headers = proxy_headers

    def _getEndpoint(self, uri):
        # save endpoint for agent to get proxy_response_headers
        self._endpoint = TunnelingHeadersTCP4ClientEndpoint(
            reactor=self._reactor,
            host=uri.host,
            port=uri.port,
            proxyConf=self._proxyConf,
            contextFactory=self._contextFactory,
            timeout=self._endpointFactory._connectTimeout,
            bindAddress=self._endpointFactory._bindAddress,
            proxy_headers=self._proxy_headers,
        )
        return self._endpoint


class ScrapyProxyHeadersAgent(ScrapyAgent):
    _TunnelingAgent = TunnelingHeadersAgent

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agent = None
        self.proxy_response_headers = None

    def _get_agent(self, request, timeout: float):
        # Scrapy 2.18+ instantiates _TunnelingAgent directly instead of
        # self._TunnelingAgent, so always build our subclass for HTTPS proxies.
        proxy = request.meta.get("proxy")
        if proxy and urlparse_cached(request).scheme == "https":
            from twisted.internet import reactor

            proxy = add_http_if_no_scheme(proxy)
            proxy_parsed = urlparse(proxy)
            proxy_host = proxy_parsed.hostname
            proxy_port = proxy_parsed.port
            if not proxy_port:
                proxy_port = 443 if proxy_parsed.scheme == "https" else 80
            if proxy_parsed.scheme == "https":
                raise NotImplementedError(
                    "HTTPS proxies for HTTPS destinations are not supported"
                )
            bindaddress = request.meta.get("bindaddress") or self._bindAddress
            try:
                from scrapy.utils._download_handlers import normalize_bind_address
                bindaddress = normalize_bind_address(bindaddress)
            except ImportError:
                pass
            proxyAuth = request.headers.get(b"Proxy-Authorization", None)
            proxyConf = (proxy_host, proxy_port, proxyAuth)
            self._agent = TunnelingHeadersAgent(
                reactor=reactor,
                proxyConf=proxyConf,
                contextFactory=self._contextFactory,
                connectTimeout=timeout,
                bindAddress=bindaddress,
                pool=self._pool,
            )
            proxy_headers = request.meta.get("proxy_headers")
            if proxy_headers:
                self._agent.set_proxy_headers(proxy_headers)
            return self._agent

        self._agent = super()._get_agent(request, timeout)
        proxy_headers = request.meta.get("proxy_headers")
        if proxy and proxy_headers and hasattr(self._agent, "set_proxy_headers"):
            self._agent.set_proxy_headers(proxy_headers)
        return self._agent

    def _cb_bodydone(self, result, *args):
        # Scrapy 2.15+ changed signature from (result, request, url) to (result, url)
        r = super()._cb_bodydone(result, *args)
        if isinstance(r, Response):
            if self._agent and hasattr(self._agent, '_endpoint'):
                proxy_response_headers = getattr(self._agent._endpoint, '_proxy_response_headers', None)
                if proxy_response_headers:
                    self.proxy_response_headers = proxy_response_headers
                    merge_proxy_response_headers(r, proxy_response_headers)
        return r
