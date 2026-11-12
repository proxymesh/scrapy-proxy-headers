"""Compatibility tests that do not use a network proxy or credentials."""

from __future__ import annotations

import doctest
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scrapy.http import Request

from scrapy_proxy_headers.connect import (
    normalize_proxy_headers,
    parse_connect_response_headers,
    proxy_cache_key,
)
from scrapy_proxy_headers.mode import PROXY_HEADERS_MODE
from tests.harness import (
    read_proxy_log,
    start_connect_proxy,
    start_https_target,
    write_self_signed_cert,
)

try:
    from scrapy.utils._download_handlers import get_proxy_headers

    from scrapy_proxy_headers.native import sent_proxy_headers
except ImportError:
    get_proxy_headers = None
    sent_proxy_headers = None

ROOT = Path(__file__).resolve().parents[1]
NATIVE = PROXY_HEADERS_MODE == "native"


def test_ci_expected_mode() -> None:
    """CI sets EXPECT_PROXY_HEADERS_MODE so a skipped master install cannot pass."""
    expected = os.environ.get("EXPECT_PROXY_HEADERS_MODE", "")
    if not expected or expected == "any":
        return
    assert PROXY_HEADERS_MODE == expected


@pytest.mark.skipif(not NATIVE, reason="Scrapy does not provide get_proxy_headers")
def test_native_sent_headers_match_scrapy() -> None:
    """The capture key must use the same header tuple Scrapy puts on CONNECT."""
    assert get_proxy_headers is not None
    assert sent_proxy_headers is not None
    request = Request(
        "https://example.com/",
        headers={"Proxy-Authorization": "Basic dTpw"},
        meta={
            "proxy": "http://user:pass@proxy.example.com:31280",
            "proxy_headers": {"X-ProxyMesh-Country": "US"},
        },
    )
    sent = get_proxy_headers(request)
    assert not any(name == "Proxy-Authorization" for name, _value in sent)
    assert sent_proxy_headers(request) == (("Proxy-Authorization", "Basic dTpw"), *sent)

    request.meta["proxy_headers"] = {
        "Proxy-Authorization": "from-meta",
        "X-ProxyMesh-Country": "US",
    }
    assert sent_proxy_headers(request) == get_proxy_headers(request)


def test_proxy_cache_key_includes_normalized_headers() -> None:
    us = proxy_cache_key("http://proxy.example.com:8080", {"X-ProxyMesh-Country": "US"})
    de = proxy_cache_key("http://proxy.example.com:8080", {"X-ProxyMesh-Country": "DE"})
    same = proxy_cache_key("proxy.example.com:8080", {"x-proxymesh-country": "US"})
    assert us != de
    assert us == same
    assert us[0] == "http://proxy.example.com:8080"
    assert normalize_proxy_headers({"B": "2", "A": "1"}) == (("a", "1"), ("b", "2"))


def test_parse_connect_response_headers_skips_status_line() -> None:
    headers = parse_connect_response_headers(
        b"HTTP/1.1 200 Connection established\r\nX-Test-Proxy: 1\r\nX-Echo-Country: US\r\n"
    )
    assert headers.get("X-Test-Proxy") == b"1"
    assert headers.get("X-Echo-Country") == b"US"
    assert headers.get("HTTP/1.1 200 Connection established") is None


def test_tunnel_request_doctest() -> None:
    result = doctest.testmod(sys.modules["scrapy_proxy_headers.connect"])
    assert result.failed == 0


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

    detail = f"exit={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    assert completed.returncode == 0, detail
    result_lines = [
        line for line in completed.stdout.splitlines() if line.startswith("RESULT ")
    ]
    assert result_lines, detail
    payload = json.loads(result_lines[-1].split(" ", 1)[1])
    assert payload["mode"] == PROXY_HEADERS_MODE, detail
    results = payload["results"]
    assert len(results) == 4, detail
    for result in results:
        assert "error" not in result, detail

    events = read_proxy_log(log_path)
    connects = [event for event in events if event["method"] == "CONNECT"]

    def countries(event: dict[str, object]) -> list[str]:
        headers = event["headers"]
        assert isinstance(headers, list)
        return [
            str(pair[1])
            for pair in headers
            if str(pair[0]).lower() == "x-proxymesh-country"
        ]

    assert [countries(event) for event in connects] == [["US"], ["DE"]], detail
    for event in connects:
        names = [str(pair[0]).lower() for pair in event["headers"]]
        assert names.count("x-proxymesh-country") == 1, detail

    for result, country in zip(results, ["US", "US", "DE", "US"]):
        assert result["headers"]["x-test-proxy"] == ["1"], detail
        assert result["headers"]["x-echo-country"] == [country], detail
        assert not any(
            key.lower() == "x-proxymesh-country" for key in result["target"]["headers"]
        ), detail
    assert sum(1 for event in connects if countries(event) == ["US"]) == 1, detail
