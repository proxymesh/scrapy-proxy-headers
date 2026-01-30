.. scrapy-proxy-headers documentation master file

Welcome to scrapy-proxy-headers's documentation!
=================================================

The ``scrapy-proxy-headers`` package is designed for adding proxy headers to HTTPS requests in `Scrapy <https://scrapy.org/>`_.

In normal usage, custom headers put in ``request.headers`` cannot be read by a proxy when you make an HTTPS request, because the headers are encrypted and passed through the proxy tunnel, along with the rest of the request body. You can read more about this at `Proxy Server Requests over HTTPS <https://docs.proxymesh.com/article/145-proxy-server-requests-over-https>`_.

Because Scrapy does not have a good way to pass custom headers to a proxy when you make HTTPS requests, we at `ProxyMesh <https://proxymesh.com>`_ made this extension to support our customers that use Scrapy and want to use custom headers to control our proxy behavior. But this extension can work for handling custom headers through any proxy.

Installation
------------

To use this extension, do the following:

1. Install the package:

   .. code-block:: bash

      pip install scrapy-proxy-headers

2. In your Scrapy ``settings.py``, add the following:

   .. code-block:: python

      DOWNLOAD_HANDLERS = {
          "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
      }

This configures Scrapy to use our custom download handler for HTTPS requests, which enables proxy header support.

Quick Start
-----------

Sending Proxy Headers
~~~~~~~~~~~~~~~~~~~~~

When you want to make a request with a custom proxy header, instead of using ``request.headers``, use ``request.meta["proxy_headers"]``:

.. code-block:: python

   import scrapy

   class MySpider(scrapy.Spider):
       name = "my_spider"
       
       def start_requests(self):
           yield scrapy.Request(
               url="https://api.ipify.org?format=json",
               meta={
                   "proxy": "http://PROXYHOST:PORT",
                   "proxy_headers": {"X-ProxyMesh-Country": "US"}
               }
           )
       
       def parse(self, response):
           # Access proxy response headers
           proxy_ip = response.headers.get("X-ProxyMesh-IP")
           self.logger.info(f"Proxy IP: {proxy_ip}")
           yield {"ip": response.json()["ip"], "proxy_ip": proxy_ip}

Receiving Proxy Response Headers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Any response headers that come from the proxy will be available in ``response.headers``:

.. code-block:: python

   def parse(self, response):
       # Proxy response headers are merged into response.headers
       proxy_ip = response.headers.get("X-ProxyMesh-IP")
       print(f"Request was made through IP: {proxy_ip}")

Proxy Headers Overview
----------------------

Proxy headers are custom HTTP headers that can be used to communicate with proxy servers. They allow you to:

* **Control proxy behavior**: Send headers like ``X-ProxyMesh-Country`` to select a specific country for your proxy connection
* **Receive proxy information**: Get headers like ``X-ProxyMesh-IP`` to know which IP address was assigned to your request
* **Maintain session consistency**: Use headers like ``X-ProxyMesh-IP`` to ensure you get the same IP address across multiple requests

The exact headers available depend on your proxy provider. Check your proxy provider's documentation for the specific headers they support.

Complete Spider Example
-----------------------

Here's a complete example spider that uses proxy headers:

.. code-block:: python

   import scrapy
   
   class ProxyHeadersSpider(scrapy.Spider):
       name = "proxy_headers_example"
       
       custom_settings = {
           "DOWNLOAD_HANDLERS": {
               "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
           }
       }
       
       def start_requests(self):
           # Request with proxy headers to select US country
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

Extension Classes
-----------------

The ``scrapy_proxy_headers`` package provides several extension classes that work together to enable proxy header support in Scrapy.

HTTP11ProxyDownloadHandler
~~~~~~~~~~~~~~~~~~~~~~~~~~

The main entry point for using proxy headers with Scrapy. This class extends ``scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler`` and should be configured in your Scrapy settings.

.. code-block:: python

   DOWNLOAD_HANDLERS = {
       "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
   }

The handler:

1. Creates a ``ScrapyProxyHeadersAgent`` for each download request
2. Manages a cache of proxy response headers by proxy URL (``_proxy_headers_by_proxy``)
3. Ensures proxy response headers are available even when tunnel connections are reused

**Why header caching is needed**: When Scrapy reuses a proxy tunnel connection for multiple requests, the proxy response headers are only available in the first response (when the tunnel is established). The handler caches these headers by proxy URL so they can be added to subsequent responses that reuse the same tunnel.

**Methods:**

* ``download_request(request, spider)`` - Downloads a request using the custom agent and ensures proxy response headers are properly cached and applied to responses.

ScrapyProxyHeadersAgent
~~~~~~~~~~~~~~~~~~~~~~~

Extends ``scrapy.core.downloader.handlers.http11.ScrapyAgent`` to use our custom tunneling agent for HTTPS requests through proxies.

.. code-block:: python

   from scrapy_proxy_headers.agent import ScrapyProxyHeadersAgent

The agent:

1. Checks if the request has both a ``proxy`` and ``proxy_headers`` in its meta
2. For HTTPS requests, configures the tunneling agent with the custom proxy headers
3. After the response body is received, merges any proxy response headers into the response

**Class Attributes:**

* ``_TunnelingAgent`` - Set to ``TunnelingHeadersAgent`` to use our custom tunneling implementation

**Methods:**

* ``_get_agent(request, timeout)`` - Returns an agent configured with proxy headers from ``request.meta["proxy_headers"]``
* ``_cb_bodydone(result, request, url)`` - Callback that merges proxy response headers into the final response

TunnelingHeadersAgent
~~~~~~~~~~~~~~~~~~~~~

Extends ``scrapy.core.downloader.handlers.http11.TunnelingAgent`` to support custom proxy headers in HTTPS tunnel establishment.

.. code-block:: python

   from scrapy_proxy_headers.agent import TunnelingHeadersAgent

The agent maintains proxy headers and creates endpoints that include them in the CONNECT request.

**Methods:**

* ``set_proxy_headers(proxy_headers)`` - Sets the proxy headers dictionary to be sent with CONNECT requests
* ``_getEndpoint(uri)`` - Creates a ``TunnelingHeadersTCP4ClientEndpoint`` configured with the proxy headers

TunnelingHeadersTCP4ClientEndpoint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Extends ``scrapy.core.downloader.handlers.http11.TunnelingTCP4ClientEndpoint`` to include custom headers in the CONNECT request and capture proxy response headers.

.. code-block:: python

   from scrapy_proxy_headers.agent import TunnelingHeadersTCP4ClientEndpoint

This is the lowest-level class that actually handles the tunnel establishment.

**Constructor Parameters:**

All standard ``TunnelingTCP4ClientEndpoint`` parameters, plus:

* ``**proxy_headers`` - Keyword arguments for additional headers to send in the CONNECT request

**Methods:**

* ``requestTunnel(protocol)`` - Sends the CONNECT request with custom proxy headers using ``tunnel_request_data_with_headers()``
* ``processProxyResponse(data)`` - Parses the proxy's CONNECT response and captures any response headers into ``_proxy_response_headers``

**Attributes:**

* ``_proxy_headers`` - Dictionary of headers to send to the proxy (includes ``Proxy-Authorization`` if configured)
* ``_proxy_response_headers`` - ``scrapy.http.Headers`` object containing headers from the proxy's CONNECT response

Helper Functions
----------------

tunnel_request_data_with_headers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Builds the binary content of a CONNECT request with custom headers.

.. code-block:: python

   from scrapy_proxy_headers.agent import tunnel_request_data_with_headers
   
   # Basic CONNECT request
   data = tunnel_request_data_with_headers("example.com", 8080)
   # Returns: b'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\n\r\n'
   
   # CONNECT request with custom headers
   data = tunnel_request_data_with_headers(
       "example.com", 8080,
       **{"X-ProxyMesh-Country": "US"}
   )
   # Returns: b'CONNECT example.com:8080 HTTP/1.1\r\nHost: example.com:8080\r\nX-ProxyMesh-Country: US\r\n\r\n'

**Parameters:**

* ``host`` (str) - The target host for the tunnel
* ``port`` (int) - The target port for the tunnel
* ``**proxy_headers`` - Additional headers to include in the CONNECT request

**Returns:**

* ``bytes`` - The complete CONNECT request as bytes, ready to send to the proxy

How It Works
------------

The extension classes work together in the following flow:

1. **HTTP11ProxyDownloadHandler** receives a download request and creates a ``ScrapyProxyHeadersAgent``

2. **ScrapyProxyHeadersAgent** checks for ``proxy`` and ``proxy_headers`` in the request meta, and configures the tunneling agent

3. **TunnelingHeadersAgent** creates a ``TunnelingHeadersTCP4ClientEndpoint`` with the proxy headers

4. **TunnelingHeadersTCP4ClientEndpoint** sends a CONNECT request with the custom headers using ``tunnel_request_data_with_headers()``

5. When the proxy responds to the CONNECT request, ``processProxyResponse()`` captures any response headers

6. After the request completes, the proxy response headers are merged into the final ``Response`` object

7. **HTTP11ProxyDownloadHandler** caches the proxy headers by proxy URL for reuse with subsequent requests on the same tunnel

This allows proxy response headers to be transparently available in your spider's ``parse`` methods without any special handling.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
