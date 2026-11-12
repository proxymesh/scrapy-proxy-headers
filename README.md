# Scrapy Proxy Headers

[![PyPI version](https://badge.fury.io/py/scrapy-proxy-headers.svg)](https://badge.fury.io/py/scrapy-proxy-headers)
[![Documentation](https://readthedocs.org/projects/scrapy-proxy-headers/badge/?version=latest)](https://scrapy-proxy-headers.readthedocs.io/)

**Send custom headers to proxies and receive proxy response headers in Scrapy.**

## The Problem

When making HTTPS requests through a proxy, headers on `request.headers` go through the encrypted tunnel and the proxy does not see them. Through Scrapy 2.19, Scrapy also does not send custom headers on the CONNECT request. Scrapy 2.20.0 does. Either way, Scrapy does not keep the proxy's CONNECT response headers, such as `X-ProxyMesh-IP`.

```
┌──────────┐     CONNECT      ┌───────┐     Encrypted     ┌────────────┐
│  Scrapy  │ ───────────────► │ Proxy │ ════════════════► │ Target URL │
└──────────┘  (unencrypted)   └───────┘    (tunnel)       └────────────┘
                  │                              │
           Proxy headers             request.headers
           go HERE                   go here (encrypted)
```

This extension solves the problem by:
1. Sending custom headers to the proxy during the CONNECT handshake
2. Capturing response headers from the proxy's CONNECT response
3. Making those headers available in your spider

## Installation

```bash
pip install scrapy-proxy-headers
```

## Quick Start

### 1. Configure the Download Handler

In your Scrapy `settings.py`:

```python
DOWNLOAD_HANDLERS = {
    "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
}
```

Or in your spider's `custom_settings`:

```python
class MySpider(scrapy.Spider):
    custom_settings = {
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
        }
    }
```

### 2. Send Proxy Headers

Use `request.meta["proxy_headers"]` to send headers to the proxy:

```python
import scrapy

class MySpider(scrapy.Spider):
    name = "example"

    async def start(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://world.proxymesh.com:31280",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            }
        )
    
    def parse(self, response):
        # Proxy response headers are available in response.headers
        proxy_ip = response.headers.get("X-ProxyMesh-IP")
        self.logger.info(f"Proxy IP: {proxy_ip}")
```

Use `async def start()`. Scrapy 2.16 removed `start_requests()`, so a spider that only defines `start_requests()` sends no requests on every Scrapy version this package supports (2.17 and newer).

`X-ProxyMesh-Country` selects a country on the ProxyMesh World proxy (`world.proxymesh.com`) and the Open proxy (`open.proxymesh.com`). It does not apply to a single-country proxy such as `us.proxymesh.com`.

### 3. Receive Proxy Response Headers

Headers from the proxy's CONNECT response are merged into `response.headers`. Headers the origin already sent are left unchanged.

```python
def parse(self, response):
    # Access headers sent by the proxy
    proxy_ip = response.headers.get(b"X-ProxyMesh-IP")
    if proxy_ip:
        print(f"Request made through IP: {proxy_ip.decode()}")
```

## Scrapy 2.20.0+ / native proxy_headers

Scrapy 2.20.0 (released 2026-11-06) is the first release with native `request.meta["proxy_headers"]` support ([#3329](https://github.com/scrapy/scrapy/issues/3329), [#7888](https://github.com/scrapy/scrapy/pull/7888)). It sends those headers to the proxy in `request.meta["proxy"]`, including on the HTTPS CONNECT request. Scrapy 2.20.0 requires Python 3.11 or newer.

scrapy-proxy-headers 0.3.0 detects that support from Scrapy's features, not from the version string. On Scrapy 2.20.0 and newer, including master, `PROXY_HEADERS_MODE` is `"native"`: Scrapy sends `proxy_headers`, and this package does not send them again. It only copies the proxy's CONNECT response headers, such as `X-ProxyMesh-IP`, onto `response.headers`. On Scrapy 2.17.0 through 2.19.x the mode is `"legacy"` and this package still writes `proxy_headers` on CONNECT itself.

Header-only users on Scrapy 2.20.0 and newer can drop the `DOWNLOAD_HANDLERS` override and keep the same meta value:

```python
yield scrapy.Request(
    url="https://api.ipify.org?format=json",
    meta={
        "proxy": "http://world.proxymesh.com:31280",
        "proxy_headers": {"X-ProxyMesh-Country": "US"},
    },
)
```

Scrapy reads the CONNECT status line and discards the rest of the proxy response headers. `X-ProxyMesh-IP` and other CONNECT response headers are still only available through this package. Keep the download handler when the spider reads them from `response.headers`:

```python
DOWNLOAD_HANDLERS = {
    "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler",
}
```

`scrapy_proxy_headers.PROXY_HEADERS_MODE` is `"native"` or `"legacy"`. It is detected from the installed Scrapy. It is not a Scrapy setting. In native mode the captured CONNECT response is merged into the Scrapy response even when Scrapy reuses the tunnel.

```python
import scrapy_proxy_headers

print(scrapy_proxy_headers.PROXY_HEADERS_MODE)
```

## Complete Example

```python
import scrapy

class ProxyHeadersSpider(scrapy.Spider):
    name = "proxy_headers_demo"
    
    custom_settings = {
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
        }
    }
    
    async def start(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://world.proxymesh.com:31280",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            },
            callback=self.parse_ip
        )
    
    def parse_ip(self, response):
        data = response.json()
        proxy_ip = response.headers.get(b"X-ProxyMesh-IP")
        
        self.logger.info(f"Public IP: {data['ip']}")
        if proxy_ip:
            self.logger.info(f"Proxy IP: {proxy_ip.decode()}")
        
        yield {
            "public_ip": data["ip"],
            "proxy_ip": proxy_ip.decode() if proxy_ip else None
        }
```

## How It Works

1. **HTTP11ProxyDownloadHandler** - Custom download handler that manages proxy header caching
2. **Legacy path** (`PROXY_HEADERS_MODE == "legacy"`) - `ScrapyProxyHeadersAgent` reads `proxy_headers` and `TunnelingHeadersAgent` sends them on CONNECT
3. **Native path** (`PROXY_HEADERS_MODE == "native"`) - Scrapy sends `proxy_headers`; the handler only records the CONNECT response

On the legacy path, `TunnelingHeadersTCP4ClientEndpoint` captures proxy response headers from the CONNECT response. On the native path, a subclass of Scrapy's tunnel protocol does that capture.

The handler caches proxy response headers by proxy URL and the normalized `proxy_headers` for that request. A reused tunnel still exposes the CONNECT response from the header set that opened it, and a different header set does not reuse another set's cached `X-ProxyMesh-IP`.

## Test Harness

A test harness is included to verify proxy header functionality:

```bash
# Basic test
PROXY_URL=http://your-proxy:port TEST_URL=https://api.ipify.org python test_proxy_headers.py

# With custom proxy header
PROXY_URL=http://your-proxy:port \
PROXY_HEADER=X-ProxyMesh-IP \
SEND_PROXY_HEADER=X-ProxyMesh-Country \
SEND_PROXY_VALUE=US \
python test_proxy_headers.py

# Verbose output
python test_proxy_headers.py -v
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXY_URL` | Proxy URL (also checks `HTTPS_PROXY`) | Required |
| `TEST_URL` | URL to request | `https://api.ipify.org?format=json` |
| `PROXY_HEADER` | Response header to check for | `X-ProxyMesh-IP` |
| `SEND_PROXY_HEADER` | Header name to send to proxy | Optional |
| `SEND_PROXY_VALUE` | Value for the send header | Optional |

## Documentation

Full documentation is available at [scrapy-proxy-headers.readthedocs.io](https://scrapy-proxy-headers.readthedocs.io/).

## Use Cases

- **Geographic targeting**: Send `X-ProxyMesh-Country` to route through specific countries
- **Session consistency**: Request the same IP across multiple requests
- **Debugging**: Capture proxy response headers to see which IP was assigned
- **Load balancing**: Use proxy headers to control request distribution

## Requirements

- Python 3.10+
- Scrapy 2.17.0+ (no upper cap). Native `proxy_headers` starts at Scrapy 2.20.0.

Scrapy 2.17.0 and 2.18 support Python 3.10 through 3.14. Scrapy 2.19 and 2.20 also list 3.15. Scrapy 2.20.0 and Scrapy master require Python 3.11+.

Local compatibility tests do not need a proxy account:

```bash
pip install -e ".[dev]"
pytest
```

## License

BSD License - see [LICENSE](LICENSE) for details.

## Links

- [PyPI](https://pypi.org/project/scrapy-proxy-headers/)
- [Documentation](https://scrapy-proxy-headers.readthedocs.io/)
- [GitHub](https://github.com/proxymesh/scrapy-proxy-headers)
- [ProxyMesh](https://proxymesh.com)
