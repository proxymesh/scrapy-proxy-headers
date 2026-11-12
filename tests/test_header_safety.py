"""CONNECT header merging, reassembly, and CRLF rejection."""

from __future__ import annotations

import pytest
from scrapy.http import Headers, Response

from scrapy_proxy_headers.connect import (
    merge_proxy_response_headers,
    parse_connect_response_headers,
)

try:
    from scrapy_proxy_headers.legacy import (
        TunnelingHeadersTCP4ClientEndpoint,
        tunnel_request_data_with_headers,
    )
except ImportError:
    TunnelingHeadersTCP4ClientEndpoint = None
    tunnel_request_data_with_headers = None

legacy_only = pytest.mark.skipif(
    tunnel_request_data_with_headers is None,
    reason="Scrapy 2.17–2.19 tunnel classes are not installed",
)


@legacy_only
def test_crlf_in_proxy_header_is_rejected() -> None:
    assert tunnel_request_data_with_headers is not None
    payload = tunnel_request_data_with_headers(
        "example.com", 443, **{"X-ProxyMesh-Country": "US"}
    )
    assert b"X-ProxyMesh-Country: US\r\n" in payload
    with pytest.raises(ValueError):
        tunnel_request_data_with_headers(
            "example.com", 443, **{"X-ProxyMesh-Country": "US\r\nX-Injected: 1"}
        )
    with pytest.raises(ValueError):
        tunnel_request_data_with_headers(
            "example.com", 443, **{"X-Good\r\nX-Injected": "1"}
        )


@legacy_only
def test_split_chunks_reassemble_headers_and_stop_at_terminator() -> None:
    assert TunnelingHeadersTCP4ClientEndpoint is not None
    endpoint = _endpoint()
    endpoint.processProxyResponse(
        b"HTTP/1.1 200 Connection established\r\nX-ProxyMesh-IP: 203.0.113.9\r\n"
    )
    assert not hasattr(endpoint, "_proxy_response_headers")
    endpoint.processProxyResponse(
        b"X-ProxyMesh-Country: US\r\n\r\nX-Injected: from-body\r\n"
    )
    headers = endpoint._proxy_response_headers
    assert headers.get("X-ProxyMesh-IP") == b"203.0.113.9"
    assert headers.get("X-ProxyMesh-Country") == b"US"
    assert headers.get("X-Injected") is None


def test_origin_headers_are_not_overwritten() -> None:
    response = Response(
        "https://example.com/",
        headers={b"Content-Type": b"text/html", b"Set-Cookie": b"session=origin"},
        body=b"ok",
    )
    merge_proxy_response_headers(
        response,
        Headers(
            {
                b"Content-Type": b"text/attacker",
                b"Set-Cookie": b"session=proxy",
                b"X-ProxyMesh-IP": b"203.0.113.9",
            }
        ),
    )
    assert response.headers.get("Content-Type") == b"text/html"
    assert response.headers.get("Set-Cookie") == b"session=origin"
    assert response.headers.get("X-ProxyMesh-IP") == b"203.0.113.9"


def test_parse_stops_at_header_terminator() -> None:
    raw = b"HTTP/1.1 200 Connection established\r\nX-ProxyMesh-IP: 203.0.113.9\r\n\r\nX-Injected: 1"
    block = raw.split(b"\r\n\r\n", 1)[0]
    headers = parse_connect_response_headers(block)
    assert headers.get("X-ProxyMesh-IP") == b"203.0.113.9"
    assert headers.get("X-Injected") is None


def _endpoint() -> TunnelingHeadersTCP4ClientEndpoint:
    class Transport:
        def startTLS(self, *args: object, **kwargs: object) -> None:
            return None

        def write(self, data: bytes) -> None:
            return None

    class Protocol:
        def __init__(self) -> None:
            self.transport = Transport()

        def dataReceived(self, data: bytes) -> None:
            return None

    class ContextFactory:
        def creatorForNetloc(self, host: str, port: int) -> object:
            return object()

    endpoint = TunnelingHeadersTCP4ClientEndpoint(
        reactor=None,
        host="example.com",
        port=443,
        proxyConf=("proxy.example", 8080, None),
        contextFactory=ContextFactory(),
    )
    endpoint._protocol = Protocol()
    endpoint._protocolDataReceived = endpoint._protocol.dataReceived
    endpoint._protocolFactory = object()
    return endpoint
