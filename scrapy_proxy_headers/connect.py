"""Shared CONNECT header parsing and cache keys."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scrapy.http import Headers, Response


def normalize_proxy_headers(
    proxy_headers: Mapping[Any, Any] | None,
) -> tuple[tuple[str, str], ...]:
    """Return ``proxy_headers`` as sorted ``(lowercase name, value)`` pairs."""
    if not proxy_headers:
        return ()
    pairs: list[tuple[str, str]] = []
    items = (
        proxy_headers.items() if isinstance(proxy_headers, Mapping) else proxy_headers
    )
    for key, value in items:
        name = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        values = value if isinstance(value, (list, tuple)) else (value,)
        for item in values:
            text = (
                item.decode("utf-8", "replace")
                if isinstance(item, bytes)
                else str(item)
            )
            pairs.append((name.lower(), text))
    return tuple(sorted(pairs))


def proxy_cache_key(
    proxy: str,
    proxy_headers: Mapping[Any, Any] | None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Cache key so different ``proxy_headers`` do not share a CONNECT response."""
    proxy = proxy.strip()
    if "://" not in proxy:
        proxy = "http://" + proxy
    return (proxy, normalize_proxy_headers(proxy_headers))


def parse_connect_response_headers(header_block: bytes) -> Headers:
    """Parse a CONNECT response, skipping the status line."""
    pairs: list[tuple[bytes, bytes]] = []
    for line in header_block.split(b"\r\n")[1:]:
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        key = key.strip()
        if key:
            pairs.append((key, value.strip()))
    return Headers(pairs)


def merge_proxy_response_headers(response: Response, proxy_headers: Headers) -> None:
    """Copy CONNECT headers the origin response does not already have."""
    for name in proxy_headers:
        if name not in response.headers:
            response.headers[name] = proxy_headers.getlist(name)
