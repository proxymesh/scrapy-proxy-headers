# Changelog

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
