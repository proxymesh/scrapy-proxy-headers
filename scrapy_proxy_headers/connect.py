"""CONNECT header bytes and proxy-header cache keys.

These helpers do not touch Scrapy downloader internals.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scrapy.http import Headers, Response
from scrapy.utils.python import to_bytes


def tunnel_request_data_with_headers(host: str, port: int, **proxy_headers: Any) -> bytes:
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


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def normalize_proxy_url(proxy: str) -> str:
    """Return *proxy* with an ``http://`` scheme when the value omits one."""
    proxy = proxy.strip()
    if "://" not in proxy:
        return "http://" + proxy
    return proxy


def normalize_proxy_headers(
    proxy_headers: Mapping[Any, Any] | None,
) -> tuple[tuple[str, str], ...]:
    """Return ``proxy_headers`` as sorted ``(lowercase name, value)`` pairs.

    Header names are compared case-insensitively. Values keep their spelling.
    A list or tuple value becomes one pair per item. ``None`` and empty
    mappings become an empty tuple.
    """
    if not proxy_headers:
        return ()
    pairs: list[tuple[str, str]] = []
    items = proxy_headers.items() if isinstance(proxy_headers, Mapping) else proxy_headers
    for key, value in items:
        name = _as_text(key).lower()
        values = value if isinstance(value, (list, tuple)) else (value,)
        for item in values:
            pairs.append((name, _as_text(item)))
    return tuple(sorted(pairs))


def proxy_cache_key(
    proxy: str,
    proxy_headers: Mapping[Any, Any] | None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Cache key for CONNECT response headers.

    Requests that share a proxy URL but send different ``proxy_headers`` must
    not reuse each other's CONNECT response (for example a different
    ``X-ProxyMesh-IP``).
    """
    return (normalize_proxy_url(proxy), normalize_proxy_headers(proxy_headers))


def parse_connect_response_headers(header_block: bytes) -> Headers:
    """Parse a CONNECT response, skipping the status line.

    *header_block* is the bytes before the blank line that ends the headers.
    """
    pairs: list[tuple[bytes, bytes]] = []
    lines = header_block.split(b"\r\n")
    for line in lines[1:]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        key = key.strip()
        if not key:
            continue
        pairs.append((key, value.strip()))
    return Headers(pairs)


def merge_proxy_response_headers(response: Response, proxy_headers: Headers) -> None:
    """Copy CONNECT response headers onto *response*.

    ``Headers.update`` replaces each name, so merging the same proxy headers
    again does not duplicate values.
    """
    if proxy_headers:
        response.headers.update(proxy_headers)
