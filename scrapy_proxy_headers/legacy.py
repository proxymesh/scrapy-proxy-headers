"""Send proxy headers on CONNECT for Scrapy 2.17 through 2.19.

Those releases tunnel with ``_TunnelingTCP4ClientEndpoint``. Scrapy 2.16+
constructs ``_TunnelingAgent`` directly, so ``ScrapyProxyHeadersAgent`` builds
that subclass itself.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from scrapy.core.downloader.handlers.http11 import (
    _ScrapyAgent,
    _TunnelingAgent,
    _TunnelingTCP4ClientEndpoint,
)
from scrapy.http import Headers, Response
from scrapy.utils._download_handlers import normalize_bind_address
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.url import add_http_if_no_scheme

from .connect import (
    merge_proxy_response_headers,
    normalize_proxy_headers,
    parse_connect_response_headers,
    tunnel_request_data_with_headers,
)


class TunnelingHeadersTCP4ClientEndpoint(_TunnelingTCP4ClientEndpoint):
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
        self._proxy_headers: dict[Any, Any] = {}
        if self._proxyAuthHeader:
            self._proxy_headers["Proxy-Authorization"] = self._proxyAuthHeader
        # Caller headers win when the name clashes with Proxy-Authorization.
        self._proxy_headers.update(proxy_headers)

    def requestTunnel(self, protocol: Any) -> Any:
        """Open the tunnel, including the custom proxy headers."""
        assert protocol.transport
        tunnel_req = tunnel_request_data_with_headers(
            self._tunneledHost,
            self._tunneledPort,
            **self._proxy_headers,
        )
        protocol.transport.write(tunnel_req)
        self._protocolDataReceived = protocol.dataReceived
        protocol.dataReceived = self.processProxyResponse  # type: ignore[method-assign]
        self._protocol = protocol
        return protocol

    def processProxyResponse(self, data: bytes) -> Any:
        """Parse the reassembled CONNECT response, stopping at the header end."""
        result = super().processProxyResponse(data)
        if b"\r\n\r\n" not in self._connectBuffer or hasattr(
            self, "_proxy_response_headers"
        ):
            return result
        header_block = bytes(self._connectBuffer).split(b"\r\n\r\n", 1)[0]
        self._proxy_response_headers = parse_connect_response_headers(header_block)
        return result


class TunnelingHeadersAgent(_TunnelingAgent):
    """Tunneling agent that opens one tunnel per proxy-header set."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy_headers: dict[Any, Any] = {}
        self._endpoint: TunnelingHeadersTCP4ClientEndpoint | None = None

    def set_proxy_headers(self, proxy_headers: dict[Any, Any]) -> None:
        """Store headers sent on the next CONNECT for this agent."""
        self._proxy_headers = proxy_headers

    def _getEndpoint(self, uri: Any) -> TunnelingHeadersTCP4ClientEndpoint:
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
        key: tuple[Any, ...],
        endpoint: Any,
        method: bytes,
        parsedURI: Any,
        headers: Any,
        bodyProducer: Any,
        requestPath: bytes,
    ) -> Any:
        # These releases pool by proxy host, port, and auth. Add the header
        # set so a later request does not reuse the first CONNECT.
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


class ScrapyProxyHeadersAgent(_ScrapyAgent):
    """Use :class:`TunnelingHeadersAgent` for HTTPS requests through a proxy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._agent: Any = None
        self.proxy_response_headers: Headers | None = None

    def _get_agent(self, request: Any, timeout: float) -> Any:
        proxy = request.meta.get("proxy")
        if proxy and urlparse_cached(request).scheme == "https":
            proxy_parsed = urlparse(add_http_if_no_scheme(proxy))
            if proxy_parsed.scheme == "https":
                raise NotImplementedError(
                    "HTTPS proxies for HTTPS destinations are not supported "
                    "on this Scrapy version"
                )
            proxy_port = proxy_parsed.port or 80
            bindaddress = normalize_bind_address(
                request.meta.get("bindaddress") or self._bindAddress
            )
            self._agent = TunnelingHeadersAgent(
                reactor=self._pool._reactor,
                proxyConf=(
                    proxy_parsed.hostname,
                    proxy_port,
                    request.headers.get(b"Proxy-Authorization", None),
                ),
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
        return self._agent

    def _cb_bodydone(self, result: Any, *args: Any) -> Any:
        response = super()._cb_bodydone(result, *args)
        agent = self._agent
        if (
            isinstance(response, Response)
            and isinstance(agent, TunnelingHeadersAgent)
            and agent._endpoint is not None
            and hasattr(agent._endpoint, "_proxy_response_headers")
        ):
            self.proxy_response_headers = agent._endpoint._proxy_response_headers
            merge_proxy_response_headers(response, self.proxy_response_headers)
        return response
