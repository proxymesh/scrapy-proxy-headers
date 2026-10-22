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
    
    def start_requests(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://your-proxy:port",
                "proxy_headers": {"X-ProxyMesh-Country": "US"}
            }
        )
    
    def parse(self, response):
        proxy_ip = response.headers.get("X-ProxyMesh-IP")
        self.logger.info(f"Proxy IP: {proxy_ip}")
```

## Receiving Proxy Response Headers

Headers from the proxy's CONNECT response are merged into `response.headers`:

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
    
    def start_requests(self):
        yield scrapy.Request(
            url="https://api.ipify.org?format=json",
            meta={
                "proxy": "http://proxy.example.com:8080",
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

## Scrapy 2.20+ / native proxy_headers

Scrapy master sends `request.meta["proxy_headers"]` on CONNECT. Header-only users can omit `DOWNLOAD_HANDLERS`. Spiders that read CONNECT response headers such as `X-ProxyMesh-IP` should keep `HTTP11ProxyDownloadHandler`. The detected path is `scrapy_proxy_headers.PROXY_HEADERS_MODE` (`native` or `legacy`). Use `http://proxy.example.com:8080` in examples. Do not put real proxy credentials in docs or tests.

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
