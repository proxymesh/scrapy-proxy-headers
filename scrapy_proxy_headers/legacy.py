"""Legacy Scrapy tunnel path (2.14.2 through 2.19.x).

Scrapy on this path does not send ``request.meta["proxy_headers"]``. The
classes below send those headers on CONNECT and keep the proxy response
headers. Private Scrapy classes are passed in from :mod:`scrapy_proxy_headers.compat`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from scrapy.http import Headers, Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.url import add_http_if_no_scheme

from .connect import (
    normalize_proxy_headers,
    parse_connect_response_headers,
    tunnel_request_data_with_headers,
)


def build_legacy_classes(
    endpoint_cls: type,
    agent_cls: type,
    scrapy_agent_cls: type,
) -> dict[str, type]:
    """Subclass the resolved Scrapy tunnel classes."""

    class TunnelingHeadersTCP4ClientEndpoint(endpoint_cls):
        """CONNECT endpoint that adds ``proxy_headers`` and stores the response."""

        def __init__(
            self,
            reactor: Any,
            host: str,
            port: int,
            proxyConf: Any,
            contextFactory: Any,
            timeout: float = 30,
            bindAddress: Any = None,
            **proxy_headers: Any,
        ) -> None:
            super().__init__(
                reactor, host, port, proxyConf, contextFactory, timeout, bindAddress
            )
            try:
                proxy_auth = self._proxyAuthHeader
            except AttributeError as exc:
                from .compat import ScrapyInternalsError

                raise ScrapyInternalsError(
                    "Scrapy's tunneling endpoint no longer sets _proxyAuthHeader. "
                    "Update scrapy_proxy_headers.legacy."
                ) from exc
            self._proxy_headers: dict[Any, Any] = {}
            if proxy_auth:
                self._proxy_headers["Proxy-Authorization"] = proxy_auth
            # Caller headers win over Proxy-Authorization when the name clashes.
            self._proxy_headers.update(proxy_headers)

        def requestTunnel(self, protocol: Any) -> Any:
            """Ask the proxy to open a tunnel, including custom proxy headers."""
            assert protocol.transport
            try:
                host = self._tunneledHost
                port = self._tunneledPort
            except AttributeError as exc:
                from .compat import ScrapyInternalsError

                raise ScrapyInternalsError(
                    "Scrapy's tunneling endpoint no longer sets _tunneledHost "
                    "and _tunneledPort. Update scrapy_proxy_headers.legacy."
                ) from exc
            tunnel_req = tunnel_request_data_with_headers(host, port, **self._proxy_headers)
            protocol.transport.write(tunnel_req)
            self._protocolDataReceived = protocol.dataReceived
            protocol.dataReceived = self.processProxyResponse  # type: ignore[method-assign]
            self._protocol = protocol
            return protocol

        def processProxyResponse(self, data: bytes) -> Any:
            # One chunk often holds the whole CONNECT response:
            # b'HTTP/1.1 200 Connection established\r\nProxy-Header: VALUE\r\n\r\n'
            header_block = data.split(b"\r\n\r\n", 1)[0]
            self._proxy_response_headers = parse_connect_response_headers(header_block)
            return super().processProxyResponse(data)

    class TunnelingHeadersAgent(agent_cls):
        """Tunneling agent that opens a tunnel per proxy-header set."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._proxy_headers: dict[Any, Any] = {}

        def set_proxy_headers(self, proxy_headers: dict[Any, Any]) -> None:
            """Store headers sent on the next CONNECT for this agent."""
            self._proxy_headers = proxy_headers

        def _getEndpoint(self, uri: Any) -> Any:
            # Kept so the agent can read CONNECT response headers after connect.
            self._endpoint = TunnelingHeadersTCP4ClientEndpoint(
                reactor=self._reactor,
                host=uri.host,
                port=uri.port,
                proxyConf=self._proxyConf,
                contextFactory=self._contextFactory,
                timeout=self._endpointFactory._connectTimeout,
                bindAddress=self._endpointFactory._bindAddress,
                **self._proxy_headers,
            )
            return self._endpoint

        def _requestWithEndpoint(
            self,
            key: Any,
            endpoint: Any,
            method: bytes,
            parsedURI: Any,
            headers: Any,
            bodyProducer: Any,
            requestPath: bytes,
        ) -> Any:
            # Released Scrapy pools tunnels by proxy host, port, and auth only.
            # Include the header set so a later request with different
            # proxy_headers opens its own CONNECT instead of reusing the first.
            if not isinstance(key, tuple):
                key = tuple(key)
            key = key + (normalize_proxy_headers(self._proxy_headers),)
            return super()._requestWithEndpoint(
                key,
                endpoint,
                method,
                parsedURI,
                headers,
                bodyProducer,
                requestPath,
            )

    class ScrapyProxyHeadersAgent(scrapy_agent_cls):
        """Scrapy agent that uses :class:`TunnelingHeadersAgent` for HTTPS proxies."""

        _TunnelingAgent = TunnelingHeadersAgent

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._agent: Any = None
            self.proxy_response_headers: Headers | None = None

        def _get_agent(self, request: Any, timeout: float) -> Any:
            # Scrapy 2.16+ instantiates _TunnelingAgent directly instead of
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
                        "HTTPS proxies for HTTPS destinations are not supported "
                        "on this Scrapy version"
                    )
                bindaddress = request.meta.get("bindaddress") or self._bindAddress
                try:
                    from scrapy.utils._download_handlers import normalize_bind_address

                    bindaddress = normalize_bind_address(bindaddress)
                except ImportError:
                    pass
                proxy_auth = request.headers.get(b"Proxy-Authorization", None)
                proxy_conf = (proxy_host, proxy_port, proxy_auth)
                self._agent = TunnelingHeadersAgent(
                    reactor=reactor,
                    proxyConf=proxy_conf,
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

        def _cb_bodydone(self, result: Any, *args: Any) -> Any:
            # Scrapy 2.15+ changed the signature from (result, request, url)
            # to (result, url).
            response = super()._cb_bodydone(result, *args)
            if isinstance(response, Response) and self._agent is not None:
                endpoint = getattr(self._agent, "_endpoint", None)
                proxy_response_headers = getattr(endpoint, "_proxy_response_headers", None)
                if proxy_response_headers:
                    response.headers.update(proxy_response_headers)
                    self.proxy_response_headers = proxy_response_headers
            return response

    return {
        "TunnelingHeadersTCP4ClientEndpoint": TunnelingHeadersTCP4ClientEndpoint,
        "TunnelingHeadersAgent": TunnelingHeadersAgent,
        "ScrapyProxyHeadersAgent": ScrapyProxyHeadersAgent,
    }
