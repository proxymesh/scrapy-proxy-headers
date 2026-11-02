#!/usr/bin/env python3
"""Tests for CONNECT header merging, reassembly, and CRLF rejection."""

import unittest

from scrapy.http import Headers, Response

from scrapy_proxy_headers.agent import (
    TunnelingHeadersTCP4ClientEndpoint,
    _merge_proxy_headers,
    tunnel_request_data_with_headers,
)


class ConnectHeaderTests(unittest.TestCase):
    def test_crlf_in_proxy_header_is_rejected(self):
        payload = tunnel_request_data_with_headers(
            "example.com", 443, **{"X-ProxyMesh-Country": "US"}
        )
        self.assertIn(b"X-ProxyMesh-Country: US\r\n", payload)

        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers(
                "example.com",
                443,
                **{"X-ProxyMesh-Country": "US\r\nX-Injected: 1"},
            )
        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers(
                "example.com", 443, **{"X-Good\r\nX-Injected": "1"}
            )

    def test_split_chunks_reassemble_headers_and_stop_at_terminator(self):
        endpoint = self._endpoint()
        endpoint.processProxyResponse(
            b"HTTP/1.1 200 Connection established\r\n"
            b"X-ProxyMesh-IP: 203.0.113.9\r\n"
        )
        self.assertFalse(hasattr(endpoint, "_proxy_response_headers"))

        endpoint.processProxyResponse(
            b"X-ProxyMesh-Country: US\r\n"
            b"\r\n"
            b"X-Injected: from-body\r\n"
        )
        headers = endpoint._proxy_response_headers
        self.assertEqual(headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")
        self.assertEqual(headers.get(b"X-ProxyMesh-Country"), b"US")
        self.assertIsNone(headers.get(b"X-Injected"))

    def test_origin_headers_are_not_overwritten(self):
        response = Response(
            url="https://example.com/",
            headers={
                b"Content-Type": b"text/html",
                b"Set-Cookie": b"session=origin",
            },
            body=b"ok",
        )
        _merge_proxy_headers(
            response,
            Headers(
                {
                    b"Content-Type": b"text/attacker",
                    b"Set-Cookie": b"session=proxy",
                    b"X-ProxyMesh-IP": b"203.0.113.9",
                }
            ),
        )
        self.assertEqual(response.headers.get(b"Content-Type"), b"text/html")
        self.assertEqual(response.headers.get(b"Set-Cookie"), b"session=origin")
        self.assertEqual(response.headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")

    def _endpoint(self):
        class Transport:
            def startTLS(self, *args, **kwargs):
                return None

            def write(self, data):
                return None

        class Protocol:
            def __init__(self):
                self.transport = Transport()

            def dataReceived(self, data):
                return None

        class ContextFactory:
            def creatorForNetloc(self, host, port):
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


if __name__ == "__main__":
    unittest.main()
