# Changelog

## Unreleased

The version in `pyproject.toml` is 0.3.0. The release date is chosen when this is published.

### Added

- On Scrapy 2.20.0 and newer, detect native `request.meta["proxy_headers"]` support and let Scrapy send those CONNECT headers. This package does not send them again. It copies the proxy's CONNECT response headers, such as `X-ProxyMesh-IP`, onto the Scrapy response.
- `scrapy_proxy_headers.PROXY_HEADERS_MODE` is `native` or `legacy`, chosen from Scrapy's features rather than the version string. `detection_details()` shows the signals used. It is not a Scrapy setting.
- Cache CONNECT response headers by proxy URL and normalized `proxy_headers`, so a different header set does not reuse another set's `X-ProxyMesh-IP`.
- On Scrapy 2.17 through 2.19, open a separate CONNECT tunnel for each `proxy_headers` set. Those releases otherwise pool tunnels by proxy host, port, and auth only.
- Local tests that run a CONNECT proxy and an HTTPS target, plus a CI matrix for Scrapy 2.17.0, 2.18.x, 2.19.0, 2.20.0, the latest PyPI release, and Scrapy master. A weekly schedule and `workflow_dispatch` re-run latest PyPI and master.

### Changed

- Remove the Scrapy `<2.20` cap added in 0.2.2. Require Scrapy >=2.17.0 with no upper cap.
- Require Python 3.10 or newer, matching Scrapy 2.17.0. Scrapy 2.20.0 and master require Python 3.11+.
- Document `async def start()`. Scrapy 2.16 removed `start_requests()`.
- Document that `X-ProxyMesh-Country` applies to the ProxyMesh World and Open proxies, not to a single-country proxy such as `us.proxymesh.com`.

## [0.2.2] - 2026-11-09

### Security

- Reject a CR or LF in a CONNECT `proxy_headers` name or value so it cannot add extra lines to the CONNECT request (#18).
- Parse the CONNECT response from the reassembled buffer and stop at the first header terminator, so a header split across TCP chunks is kept (#18).
- Leave origin headers already on the HTTPS response unchanged when CONNECT headers are merged. New proxy headers such as `X-ProxyMesh-IP` are still copied (#18).
- Raise the Scrapy minimum from 2.14.2 to 2.17.0 so installs include the fix for CVE-2026-84366 / GHSA-76g3-c3x4-crvx (signed `s3://` requests sent over plaintext HTTP) (#17).

### Changed

- Require Scrapy >=2.17.0,<2.20. Scrapy 2.20.0 (2026-11-06) removed `_TunnelingTCP4ClientEndpoint`, which this release still imports. Native `proxy_headers` support is not part of 0.2.2.
- Run `test_header_safety.py` in the proxy integration job (#18).
- Document that CONNECT headers do not overwrite headers the origin already sent.
- Pin GitHub Actions jobs to `ubuntu-24.04` (#15).
- Group Dependabot updates and auto-merge Dependabot version updates, including GitHub Actions bumps (#11, #13, #14).
