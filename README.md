# Scrapy Proxy Headers

[![PyPI version](https://badge.fury.io/py/scrapy-proxy-headers.svg)](https://badge.fury.io/py/scrapy-proxy-headers)
[![Documentation](https://readthedocs.org/projects/scrapy-proxy-headers/badge/?version=latest)](https://scrapy-proxy-headers.readthedocs.io/)

**Send custom headers to proxies and receive proxy response headers in Scrapy.**

## The Problem

When making HTTPS requests through a proxy, Scrapy cannot send custom headers to the proxy itself. This is because HTTPS requests create an encrypted tunnel (via HTTP CONNECT) - any headers you add to `request.headers` are encrypted and only visible to the destination server, not the proxy.

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
    
    def start_requests(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://your-proxy:port",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            }
        )
    
    def parse(self, response):
        # Proxy response headers are available in response.headers
        proxy_ip = response.headers.get("X-ProxyMesh-IP")
        self.logger.info(f"Proxy IP: {proxy_ip}")
```

### 3. Receive Proxy Response Headers

Headers from the proxy's CONNECT response are automatically merged into `response.headers`:

```python
def parse(self, response):
    # Access headers sent by the proxy
    proxy_ip = response.headers.get(b"X-ProxyMesh-IP")
    if proxy_ip:
        print(f"Request made through IP: {proxy_ip.decode()}")
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
    
    def start_requests(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://us.proxymesh.com:31280",
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
2. **ScrapyProxyHeadersAgent** - Agent that reads `proxy_headers` from request meta
3. **TunnelingHeadersAgent** - Sends custom headers in the CONNECT request
4. **TunnelingHeadersTCP4ClientEndpoint** - Captures proxy response headers from CONNECT response

The handler also caches proxy response headers by proxy URL. This ensures headers remain available even when Scrapy reuses existing tunnel connections for subsequent requests.

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

- Python 3.8+
- Scrapy 2.0+

## License

BSD License - see [LICENSE](LICENSE) for details.

## Links

- [PyPI](https://pypi.org/project/scrapy-proxy-headers/)
- [Documentation](https://scrapy-proxy-headers.readthedocs.io/)
- [GitHub](https://github.com/proxymesh/scrapy-proxy-headers)
- [ProxyMesh](https://proxymesh.com)
