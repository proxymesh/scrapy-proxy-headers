The `scrapy-proxy-headers` package is designed for adding proxy headers to HTTPS requests.

In normal usage, custom headers put in `request.headers` cannot be read by a proxy when you make a HTTPS request, because the headers are encrypted and passed through the proxy tunnel, along with the rest of the request body. You can read more about this at [Proxy Server Requests over HTTPS](https://docs.proxymesh.com/article/145-proxy-server-requests-over-https).

Because Scrapy does not have a good way to pass custom headers to a proxy when you make HTTPS requests, we at [ProxyMesh](https://proxymesh.com) made this extension to support our customers that use Scrapy and want to use custom headers to control our proxy behavior. But this extension can work for any custom headers through a proxy.

To use this extension, do the following:

1. `pip install scrapy-proxy-headers`
2. In your Scrapy `settings.py`, add the following code:

```python
DOWNLOAD_HANDLERS = {
  "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
}
```

3. When you want make a request with a custom proxy header, instead of using `request.headers`, use `request.meta["proxy_headers"]` like this:

```python
request.meta["proxy_headers"] = {"X-ProxyMesh-Country": "US"}
```

Currently this package does not yet support reading custom response headers from the proxy, but that feature is coming soon.