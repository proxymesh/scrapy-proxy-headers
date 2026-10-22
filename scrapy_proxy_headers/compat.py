"""Scrapy private-API compatibility.

All access to Scrapy downloader internals lives in this module. A future
Scrapy that moves these symbols should fail here with
:class:`ScrapyInternalsError` instead of an ``AttributeError`` at an
unrelated import.
"""

from __future__ import annotations

import inspect
from typing import Any

import scrapy
from scrapy.http import Headers

from .connect import parse_connect_response_headers

NATIVE = "native"
LEGACY = "legacy"

_CAPTURED: dict[tuple[Any, ...], Headers] = {}
_LEGACY_CLASSES: dict[str, type] | None = None
_DETAILS: dict[str, Any] = {}


class ScrapyInternalsError(RuntimeError):
    """Scrapy downloader internals no longer match what this package expects."""


def _has_get_proxy_headers() -> bool:
    try:
        from scrapy.utils import _download_handlers as handlers
    except ImportError:
        return False
    return callable(getattr(handlers, "get_proxy_headers", None))


def _legacy_endpoint_names(http11: Any) -> bool:
    return hasattr(http11, "TunnelingTCP4ClientEndpoint") or hasattr(
        http11, "_TunnelingTCP4ClientEndpoint"
    )


def _require_legacy_bases() -> tuple[type, type, type]:
    import scrapy.core.downloader.handlers.http11 as http11

    endpoint = getattr(http11, "TunnelingTCP4ClientEndpoint", None) or getattr(
        http11, "_TunnelingTCP4ClientEndpoint", None
    )
    agent = getattr(http11, "TunnelingAgent", None) or getattr(http11, "_TunnelingAgent", None)
    scrapy_agent = getattr(http11, "ScrapyAgent", None) or getattr(http11, "_ScrapyAgent", None)
    missing = [
        name
        for name, value in (
            ("TunnelingTCP4ClientEndpoint", endpoint),
            ("TunnelingAgent", agent),
            ("ScrapyAgent", scrapy_agent),
        )
        if value is None
    ]
    if missing:
        raise ScrapyInternalsError(
            f"Scrapy {scrapy.__version__} is missing legacy tunnel symbols {missing}. "
            "Native proxy_headers support was not detected either "
            "(scrapy.utils._download_handlers.get_proxy_headers and "
            "http11._TunnelProtocol). Update scrapy_proxy_headers.compat."
        )
    contracts = (
        (endpoint, ("requestTunnel", "processProxyResponse")),
        (agent, ("_getEndpoint", "_requestWithEndpoint")),
        (scrapy_agent, ("_get_agent", "_cb_bodydone")),
    )
    for cls, methods in contracts:
        absent = [method for method in methods if not hasattr(cls, method)]
        if absent:
            raise ScrapyInternalsError(
                f"Scrapy {cls.__name__} is missing {absent}. "
                "Tunnel internals changed; update scrapy_proxy_headers.compat."
            )
    return endpoint, agent, scrapy_agent


def _install_native_capture() -> None:
    """Replace ``http11._TunnelProtocol`` with a subclass that records CONNECT headers.

    ``_TunnelFactory.buildProtocol`` looks the class up on the module at call
    time, so replacing the global is enough. Scrapy's ``connectionMade`` still
    writes the CONNECT request, which avoids sending ``proxy_headers`` twice.
    """
    import scrapy.core.downloader.handlers.http11 as http11

    original = getattr(http11, "_TunnelProtocol", None)
    if original is None or not inspect.isclass(original):
        raise ScrapyInternalsError(
            f"Scrapy {scrapy.__version__} has get_proxy_headers but no "
            "http11._TunnelProtocol class. Update scrapy_proxy_headers.compat."
        )
    if getattr(original, "_sph_capturing", False):
        return
    parameters = inspect.signature(original.__init__).parameters
    required = ("proxyHost", "proxyPort", "proxyHeaders")
    missing = [name for name in required if name not in parameters]
    if missing or not callable(getattr(original, "dataReceived", None)):
        raise ScrapyInternalsError(
            "Scrapy _TunnelProtocol does not expose "
            f"{missing or ['dataReceived']}, which scrapy-proxy-headers needs "
            "to capture CONNECT response headers. Update scrapy_proxy_headers.compat."
        )

    class _CapturingTunnelProtocol(original):  # type: ignore[valid-type,misc]
        _sph_capturing = True

        def dataReceived(self, data: bytes) -> None:
            ready_before = bool(getattr(self, "_tunnelReady", False))
            super().dataReceived(data)
            if ready_before or getattr(self, "_sph_captured", False):
                return
            if not getattr(self, "_tunnelReady", False):
                return
            self._sph_captured = True
            _record_from_protocol(self)

    http11._TunnelProtocol = _CapturingTunnelProtocol


def _record_from_protocol(protocol: Any) -> None:
    try:
        buffer = bytes(protocol._connectBuffer)
        host = protocol._proxyHost
        port = protocol._proxyPort
        sent = protocol._proxyHeaders
    except AttributeError as exc:
        raise ScrapyInternalsError(
            "Scrapy _TunnelProtocol no longer exposes _connectBuffer, "
            "_proxyHost, _proxyPort, and _proxyHeaders. Update "
            f"scrapy_proxy_headers.compat ({exc})."
        ) from exc
    header_block, separator, _rest = buffer.partition(b"\r\n\r\n")
    if not separator:
        return
    _CAPTURED[_capture_key(host, port, sent)] = parse_connect_response_headers(header_block)


def _as_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _capture_key(host: Any, port: Any, proxy_headers: Any) -> tuple[Any, ...]:
    frozen = tuple((_as_str(name), _as_str(value)) for name, value in proxy_headers)
    return (_as_str(host).lower(), int(port), frozen)


def _proxy_host_port(proxy: str) -> tuple[str, int]:
    from urllib.parse import urlparse

    from scrapy.utils.url import add_http_if_no_scheme

    parsed = urlparse(add_http_if_no_scheme(proxy))
    host = parsed.hostname
    if not host:
        raise ScrapyInternalsError(f"Cannot parse proxy URL {proxy!r}.")
    if parsed.port:
        port = parsed.port
    else:
        port = 443 if parsed.scheme == "https" else 80
    return host, port


def _sent_proxy_headers(request: Any) -> tuple[tuple[str, str], ...]:
    """Rebuild the header tuple Scrapy passes to ``_TunnelProtocol``.

    This mirrors ``_ScrapyAgent._get_agent``: ``get_proxy_headers(request)``,
    then ``Proxy-Authorization`` from the request headers when that name is
    absent. ``proxy_headers`` wins when it already contains that name.
    """
    try:
        from scrapy.utils._download_handlers import get_proxy_headers
    except ImportError as exc:
        raise ScrapyInternalsError(
            "Native mode requires scrapy.utils._download_handlers.get_proxy_headers. "
            "Update scrapy_proxy_headers.compat."
        ) from exc
    headers = tuple((_as_str(name), _as_str(value)) for name, value in get_proxy_headers(request))
    auth = request.headers.get(b"Proxy-Authorization", None)
    if auth and not any(name == "Proxy-Authorization" for name, _value in headers):
        if isinstance(auth, bytes):
            auth_text = auth.decode()
        else:
            auth_text = str(auth)
        headers = (("Proxy-Authorization", auth_text), *headers)
    return headers


def _native_registry_key(request: Any) -> tuple[Any, ...]:
    proxy = request.meta.get("proxy")
    if not proxy:
        raise ScrapyInternalsError("Cannot look up CONNECT headers without a proxy URL.")
    host, port = _proxy_host_port(proxy)
    return _capture_key(host, port, _sent_proxy_headers(request))


def lookup_connect_response_headers(request: Any) -> Headers | None:
    """Return CONNECT response headers captured for *request*, if any.

    On legacy Scrapy this is always ``None``; the legacy agent stores headers
    on the endpoint instead.
    """
    if PROXY_HEADERS_MODE != NATIVE:
        return None
    if not request.meta.get("proxy"):
        return None
    return _CAPTURED.get(_native_registry_key(request))


def explain_capture_miss(request: Any) -> str:
    """Describe a native capture-key miss for logs."""
    try:
        expected = _native_registry_key(request)
    except Exception as exc:  # noqa: BLE001 - diagnostic string for the warning
        expected = f"<error {exc}>"
    return f"expected={expected!r} captured={list(_CAPTURED)!r}"


def legacy_classes() -> dict[str, type]:
    """Return legacy tunnel subclasses. Raises in native mode."""
    if _LEGACY_CLASSES is None:
        raise ScrapyInternalsError(
            "Legacy tunnel classes are not available because this Scrapy "
            f"({scrapy.__version__}) sends proxy_headers itself "
            f"(mode={PROXY_HEADERS_MODE!r})."
        )
    return _LEGACY_CLASSES


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("scrapy-proxy-headers")
    except Exception:
        return "unknown"


def _detect() -> str:
    import scrapy.core.downloader.handlers.http11 as http11

    has_helper = _has_get_proxy_headers()
    has_protocol = hasattr(http11, "_TunnelProtocol")
    has_legacy = _legacy_endpoint_names(http11)
    if has_helper and has_protocol:
        mode = NATIVE
    elif has_legacy:
        mode = LEGACY
    else:
        raise ScrapyInternalsError(
            f"scrapy-proxy-headers does not recognize Scrapy {scrapy.__version__}. "
            "Expected native proxy_headers support "
            "(scrapy.utils._download_handlers.get_proxy_headers and "
            "http11._TunnelProtocol) or the legacy TunnelingTCP4ClientEndpoint "
            "family. Update scrapy_proxy_headers.compat."
        )
    _DETAILS.update(
        {
            "mode": mode,
            "scrapy_version": scrapy.__version__,
            "package_version": _package_version(),
            "has_get_proxy_headers": has_helper,
            "has_tunnel_protocol": has_protocol,
            "has_legacy_endpoint": has_legacy,
        }
    )
    return mode


def detection_details() -> dict[str, Any]:
    """Return the feature signals used to choose :data:`PROXY_HEADERS_MODE`."""
    return dict(_DETAILS)


def get_proxy_headers_mode() -> str:
    """Return ``native`` or ``legacy`` for the detected Scrapy integration.

    ``native``
        Scrapy sends ``request.meta["proxy_headers"]``. This package only
        captures CONNECT response headers.
    ``legacy``
        Scrapy does not send those headers. This package sends them on
        CONNECT and captures the proxy response, as in 0.2.x.
    """
    return PROXY_HEADERS_MODE


def _load() -> str:
    global _LEGACY_CLASSES
    mode = _detect()
    if mode == NATIVE:
        _install_native_capture()
        return mode
    from .legacy import build_legacy_classes

    _LEGACY_CLASSES = build_legacy_classes(*_require_legacy_bases())
    return mode


PROXY_HEADERS_MODE = _load()
