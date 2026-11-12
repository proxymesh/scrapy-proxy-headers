---
name: scrapy-proxy-headers
description: >-
  Send and receive custom headers during HTTPS CONNECT tunneling in Scrapy.
  Use when adding proxy headers to Scrapy spiders, configuring download handlers
  for proxy header support, or reading proxy response headers like X-ProxyMesh-IP.
---

# scrapy-proxy-headers

Send custom headers to proxies and receive proxy response headers in Scrapy.

## Installation

```bash
pip install scrapy-proxy-headers
```

## Configuration

Add the download handler in `settings.py`:

```python
DOWNLOAD_HANDLERS = {
    "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
}
```

Or in spider's `custom_settings`:

```python
class MySpider(scrapy.Spider):
    custom_settings = {
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
        }
    }
```

## Sending Proxy Headers

Use `request.meta["proxy_headers"]`:

```python
import scrapy

class MySpider(scrapy.Spider):
    name = "example"
    
    async def start(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://user:pass@proxy.example.com:31280",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            }
        )
    
    def parse(self, response):
        proxy_ip = response.headers.get("X-ProxyMesh-IP")
        self.logger.info(f"Proxy IP: {proxy_ip}")
```

Use `async def start()`. Scrapy 2.16 removed `start_requests()`. `X-ProxyMesh-Country` is only honored by some ProxyMesh proxies. See the [ProxyMesh docs](https://docs.proxymesh.com/).

## Receiving Proxy Response Headers

Headers from the proxy's CONNECT response are merged into `response.headers`. Headers the origin already sent are left unchanged.

```python
def parse(self, response):
    proxy_ip = response.headers.get(b"X-ProxyMesh-IP")
    if proxy_ip:
        print(f"Request made through IP: {proxy_ip.decode()}")
```

Note: Headers are bytes in Scrapy; decode with `.decode()`.

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
                "proxy": "http://user:pass@proxy.example.com:31280",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            },
            callback=self.parse_ip
        )
    
    def parse_ip(self, response):
        data = response.json()
        proxy_ip = response.headers.get(b"X-ProxyMesh-IP")
        
        yield {
            "public_ip": data["ip"],
            "proxy_ip": proxy_ip.decode() if proxy_ip else None
        }
```

## Scrapy 2.20.0+ / native proxy_headers

Scrapy 2.20.0 (2026-11-06) is the first release with native `request.meta["proxy_headers"]` (`#3329`, `#7888`). It requires Python 3.11+. scrapy-proxy-headers 0.3.0 detects that support by feature, not version. On 2.20.0 and newer, `PROXY_HEADERS_MODE` is `native`: Scrapy sends the headers, and this package only copies CONNECT response headers such as `X-ProxyMesh-IP` onto `response.headers`. Header-only users can omit `DOWNLOAD_HANDLERS`. On 2.17.0 through 2.19.x the mode is `legacy` and this package still writes the CONNECT headers. `PROXY_HEADERS_MODE` is detected, not a Scrapy setting. `X-ProxyMesh-Country` is only honored by some ProxyMesh proxies; see https://docs.proxymesh.com/. Use `http://user:pass@proxy.example.com:31280` in examples. Do not put a real proxy host or real credentials in docs or tests.

## Proxy Headers

Custom headers sent during CONNECT are proxy-specific. Check your proxy provider's docs.

Example with [ProxyMesh](https://proxymesh.com):

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-ProxyMesh-Country` | Send | Route through specific country |
| `X-ProxyMesh-IP` | Send/Receive | Request or receive sticky IP |

## Testing

```bash
PROXY_URL=http://your-proxy:port python test_proxy_headers.py -v
```

## Documentation

Full docs at [scrapy-proxy-headers.readthedocs.io](https://scrapy-proxy-headers.readthedocs.io/).
