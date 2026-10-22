"""Compatibility tests that do not use a network proxy or credentials."""

from __future__ import annotations

import doctest
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import scrapy
import scrapy.core.downloader.handlers.http11 as http11

import scrapy_proxy_headers
from scrapy_proxy_headers.connect import (
    normalize_proxy_headers,
    parse_connect_response_headers,
    proxy_cache_key,
    tunnel_request_data_with_headers,
)
from scrapy_proxy_headers.compat import ScrapyInternalsError
from tests.harness import (
    read_proxy_log,
    start_connect_proxy,
    start_https_target,
    write_self_signed_cert,
)

ROOT = Path(__file__).resolve().parents[1]


def _expected_mode() -> str:
    try:
        from scrapy.utils._download_handlers import get_proxy_headers
    except ImportError:
        get_proxy_headers = None  # type: ignore[assignment]
    has_helper = callable(get_proxy_headers)
    has_protocol = hasattr(http11, "_TunnelProtocol")
    has_legacy = hasattr(http11, "TunnelingTCP4ClientEndpoint") or hasattr(
        http11, "_TunnelingTCP4ClientEndpoint"
    )
    if has_helper and has_protocol:
        return "native"
    if has_legacy:
        return "legacy"
    raise AssertionError("Scrapy tunnel implementation was not recognized")


def _values(headers: dict[str, list[str]], name: str) -> list[str]:
    found: list[str] = []
    for key, values in headers.items():
        if key.lower() == name.lower():
            found.extend(values)
    return found


def test_ci_expected_mode() -> None:
    """CI sets EXPECT_PROXY_HEADERS_MODE so a skipped master install cannot pass."""
    expected = os.environ.get("EXPECT_PROXY_HEADERS_MODE", "")
    if not expected or expected == "any":
        return
    assert scrapy_proxy_headers.PROXY_HEADERS_MODE == expected, (
        scrapy_proxy_headers.detection_details()
    )


def test_detected_mode_matches_scrapy_features() -> None:
    assert scrapy_proxy_headers.get_proxy_headers_mode() == _expected_mode()
    assert scrapy_proxy_headers.PROXY_HEADERS_MODE == _expected_mode()
    details = scrapy_proxy_headers.detection_details()
    assert details["mode"] == _expected_mode()
    assert details["scrapy_version"] == scrapy.__version__


def test_legacy_symbols_follow_the_detected_mode() -> None:
    if _expected_mode() == "legacy":
        from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent

        assert ScrapyProxyHeadersAgent.__name__ == "ScrapyProxyHeadersAgent"
        return
    with pytest.raises(ScrapyInternalsError):
        from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent


def test_proxy_cache_key_includes_normalized_headers() -> None:
    us = proxy_cache_key(
        "http://proxy.example.com:8080",
        {"X-ProxyMesh-Country": "US"},
    )
    de = proxy_cache_key(
        "http://proxy.example.com:8080",
        {"X-ProxyMesh-Country": "DE"},
    )
    same = proxy_cache_key(
        "proxy.example.com:8080",
        {"x-proxymesh-country": "US"},
    )
    assert us != de
    assert us == same
    assert us[0] == "http://proxy.example.com:8080"
    assert normalize_proxy_headers({"B": "2", "A": "1"}) == (("a", "1"), ("b", "2"))


def test_parse_connect_response_headers_skips_status_line() -> None:
    raw = (
        b"HTTP/1.1 200 Connection established\r\n"
        b"X-Test-Proxy: 1\r\n"
        b"X-Echo-Country: US\r\n"
    )
    headers = parse_connect_response_headers(raw)
    assert _header(headers, "X-Test-Proxy") == b"1"
    assert _header(headers, "X-Echo-Country") == b"US"
    assert _header(headers, "HTTP/1.1 200 Connection established") is None


def test_tunnel_request_doctest() -> None:
    result = doctest.testmod(sys.modules["scrapy_proxy_headers.connect"])
    assert result.failed == 0
    payload = tunnel_request_data_with_headers(
        "example.com",
        443,
        **{"X-ProxyMesh-Country": "US"},
    )
    assert payload.count(b"X-ProxyMesh-Country: US") == 1


def _header(headers: object, name: str) -> bytes | None:
    from scrapy.http import Headers

    assert isinstance(headers, Headers)
    wanted = name.lower()
    for key, values in headers.items():
        text = key.decode() if isinstance(key, bytes) else str(key)
        if text.lower() == wanted and values:
            value = values[-1]
            return value if isinstance(value, bytes) else str(value).encode()
    return None


def test_connect_headers_cache_and_reuse(tmp_path: Path) -> None:
    cert, key = write_self_signed_cert(tmp_path)
    log_path = tmp_path / "connect.log"
    target_port, stop_target = start_https_target(cert, key)
    proxy_port, stop_proxy = start_connect_proxy(log_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "proxy": f"http://127.0.0.1:{proxy_port}",
                "target_base": f"https://127.0.0.1:{target_port}",
                "steps": ["US", "US", "DE", "US"],
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")])
    try:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "run_crawl.py"), str(plan_path)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    finally:
        stop_proxy()
        stop_target()

    result_lines = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
    detail = (
        f"exit={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert completed.returncode == 0, detail
    assert result_lines, detail
    payload = json.loads(result_lines[-1].split(" ", 1)[1])
    assert payload["mode"] == _expected_mode(), detail
    results = payload["results"]
    assert len(results) == 4, detail
    for result in results:
        assert "error" not in result, detail

    events = read_proxy_log(log_path)
    connects = [event for event in events if event["method"] == "CONNECT"]

    def countries(event: dict[str, object]) -> list[str]:
        found = []
        headers = event["headers"]
        assert isinstance(headers, list)
        for pair in headers:
            assert isinstance(pair, list)
            if str(pair[0]).lower() == "x-proxymesh-country":
                found.append(str(pair[1]))
        return found

    # (a) custom header arrives once per CONNECT, (c) no duplicate header lines.
    assert [countries(event) for event in connects] == [["US"], ["DE"]], detail
    for event in connects:
        names = [str(pair[0]).lower() for pair in event["headers"]]
        assert names.count("x-proxymesh-country") == 1, detail

    expected = ["US", "US", "DE", "US"]
    for result, country in zip(results, expected):
        headers = result["headers"]
        # (b) proxy response header is visible, once.
        assert _values(headers, "X-Test-Proxy") == ["1"], detail
        # (d) cached response headers follow the header set, not the proxy URL alone.
        assert _values(headers, "X-Echo-Country") == [country], detail
        target_headers = {
            str(key).lower(): value for key, value in result["target"]["headers"].items()
        }
        assert "x-proxymesh-country" not in target_headers, detail

    # (e) the second and fourth US requests reuse the US tunnel.
    assert sum(1 for event in connects if countries(event) == ["US"]) == 1, detail
