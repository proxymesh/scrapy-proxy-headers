# Changelog

## Unreleased

The version in `pyproject.toml` is 0.3.0. The release date and final version are chosen when this draft is published.

### Added

- Detect whether Scrapy sends `request.meta["proxy_headers"]` itself. Detection uses `scrapy.utils._download_handlers.get_proxy_headers` and `http11._TunnelProtocol`, not a version string.
- On that native implementation (Scrapy master, expected in the 2.20 line), let Scrapy send the CONNECT headers and only capture the proxy's CONNECT response headers, including `X-ProxyMesh-IP`.
- Expose the detected mode as `scrapy_proxy_headers.PROXY_HEADERS_MODE` and `get_proxy_headers_mode()` (`native` or `legacy`) plus `detection_details()` for debugging.
- Local pytest coverage for CONNECT header delivery, proxy response headers, duplicate headers, per-header-set caching, and tunnel reuse. No proxy credentials are required.
- GitHub Actions matrix for Scrapy 2.14.2, 2.18.x, 2.19.0, the latest PyPI release, and Scrapy master, across the CPython versions those releases support. A weekly schedule re-runs the Scrapy master cells.

### Fixed

- Cache CONNECT response headers by proxy URL and normalized `proxy_headers`, so a request with a different header set does not receive another set's cached response headers.
- On Scrapy 2.14.2 through 2.19.x, open a separate CONNECT tunnel per `proxy_headers` set. Those releases pool tunnels by proxy host, port, and auth only, which dropped later header sets on the floor.

### Changed

- Require Python 3.10 or newer, matching Scrapy 2.14.2.
- Keep the dependency as `scrapy>=2.14.2` with no upper cap, so the upcoming Scrapy release stays installable.
- Private Scrapy downloader access is isolated in `scrapy_proxy_headers.compat` and raises `ScrapyInternalsError` when those internals move again.
