#!/usr/bin/env python3
"""Unit tests for CONNECT header sanitization and origin-header isolation."""

import unittest

from scrapy.http import Headers, Request, Response

from scrapy_proxy_headers.agent import (
    TunnelingHeadersTCP4ClientEndpoint,
    merge_proxy_response_headers,
    parse_connect_response_headers,
    tunnel_request_data_with_headers,
)


class TunnelRequestCrlfTests(unittest.TestCase):
    def test_valid_header_is_emitted(self):
        payload = tunnel_request_data_with_headers(
            "example.com", 443, **{"X-ProxyMesh-Country": "US"}
        )
        self.assertIn(b"X-ProxyMesh-Country: US\r\n", payload)
        self.assertTrue(payload.endswith(b"\r\n\r\n"))

    def test_crlf_in_value_is_rejected(self):
        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers(
                "example.com",
                443,
                **{
                    "X-ProxyMesh-Country": (
                        "US\r\nX-Injected: smuggled\r\n"
                        "Proxy-Authorization: Basic YXR0YWNrZXI="
                    )
                },
            )

    def test_crlf_in_name_is_rejected(self):
        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers(
                "example.com", 443, **{"X-Good\r\nX-Injected": "1"}
            )

    def test_nul_in_value_is_rejected(self):
        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers(
                "example.com", 443, **{"X-ProxyMesh-Country": "US\x00UK"}
            )

    def test_crlf_in_host_is_rejected(self):
        with self.assertRaises(ValueError):
            tunnel_request_data_with_headers("example.com\r\nX-Injected: 1", 443)


class ConnectResponseReassemblyTests(unittest.TestCase):
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

    def test_split_chunks_keep_headers_and_ignore_bytes_after_terminator(self):
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
            b"Set-Cookie: session=from-body\r\n"
            b"\r\n"
        )
        headers = endpoint._proxy_response_headers
        self.assertEqual(headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")
        self.assertEqual(headers.get(b"X-ProxyMesh-Country"), b"US")
        self.assertIsNone(headers.get(b"X-Injected"))
        self.assertIsNone(headers.get(b"Set-Cookie"))


class ConnectResponseParseTests(unittest.TestCase):
    def test_stops_at_header_terminator(self):
        data = (
            b"HTTP/1.1 200 Connection established\r\n"
            b"X-ProxyMesh-IP: 203.0.113.9\r\n"
            b"Set-Cookie: session=attacker\r\n"
            b"\r\n"
            b"this-is-not-a-header: ignored\r\n"
        )
        headers = parse_connect_response_headers(data)
        self.assertEqual(headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")
        self.assertEqual(headers.get(b"Set-Cookie"), b"session=attacker")
        self.assertIsNone(headers.get(b"this-is-not-a-header"))


class MergeProxyResponseHeaderTests(unittest.TestCase):
    def _origin_response(self) -> tuple[Request, Response]:
        request = Request("https://example.com/account")
        response = Response(
            url="https://example.com/account",
            status=200,
            headers={
                b"Content-Type": [b"text/html; charset=utf-8"],
                b"Set-Cookie": [b"session=legitimate-origin"],
            },
            body=b"<html>ok</html>",
            request=request,
        )
        return request, response

    def test_set_cookie_from_connect_is_not_copied(self):
        request, response = self._origin_response()
        connect = Headers(
            {
                b"Set-Cookie": b"session=attacker-controlled",
                b"X-ProxyMesh-IP": b"203.0.113.9",
            }
        )
        merge_proxy_response_headers(response, connect, request=request)
        self.assertEqual(
            response.headers.getlist(b"Set-Cookie"),
            [b"session=legitimate-origin"],
        )
        self.assertEqual(response.headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")
        self.assertEqual(
            response.meta["proxy_response_headers"].get(b"Set-Cookie"),
            b"session=attacker-controlled",
        )

    def test_does_not_overwrite_origin_content_type(self):
        request, response = self._origin_response()
        connect = Headers({b"Content-Type": b"text/attacker"})
        merge_proxy_response_headers(response, connect, request=request)
        self.assertEqual(
            response.headers.get(b"Content-Type"),
            b"text/html; charset=utf-8",
        )

    def test_merge_without_request_still_filters_headers(self):
        response = Response(
            url="https://example.com/account",
            status=200,
            headers={b"Set-Cookie": [b"session=legitimate-origin"]},
            body=b"<html>ok</html>",
        )
        connect = Headers(
            {
                b"Set-Cookie": b"session=attacker-controlled",
                b"X-ProxyMesh-IP": b"203.0.113.9",
            }
        )
        merge_proxy_response_headers(response, connect)
        self.assertEqual(
            response.headers.getlist(b"Set-Cookie"),
            [b"session=legitimate-origin"],
        )
        self.assertEqual(response.headers.get(b"X-ProxyMesh-IP"), b"203.0.113.9")

    def test_referrer_policy_from_connect_is_not_copied(self):
        request, response = self._origin_response()
        connect = Headers({b"Referrer-Policy": b"sys.exit"})
        merge_proxy_response_headers(response, connect, request=request)
        self.assertIsNone(response.headers.get(b"Referrer-Policy"))
        self.assertEqual(
            response.meta["proxy_response_headers"].get(b"Referrer-Policy"),
            b"sys.exit",
        )


if __name__ == "__main__":
    unittest.main()
