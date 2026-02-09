#!/usr/bin/env python3
"""
Test harness for scrapy-proxy-headers.

Tests that the extension can send custom headers to a proxy and receive
response headers from the proxy's CONNECT response.

Environment Variables:
    PROXY_URL       - Proxy URL (also checks HTTPS_PROXY). Required.
    TEST_URL        - URL to request (default: https://api.ipify.org?format=json)
    PROXY_HEADER    - Response header to check for (default: X-ProxyMesh-IP)
    SEND_PROXY_HEADER - Optional header name to send to proxy
    SEND_PROXY_VALUE  - Optional value for the send header

Usage:
    PROXY_URL=http://your-proxy:port python test_proxy_headers.py
    PROXY_URL=http://your-proxy:port python test_proxy_headers.py -v
"""

import os
import sys
import argparse

# Scrapy imports
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


class ProxyHeaderTestSpider(scrapy.Spider):
    """Spider that tests proxy header functionality."""
    
    name = "proxy_header_test"
    
    custom_settings = {
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
        },
        "LOG_LEVEL": "WARNING",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    }
    
    def __init__(self, proxy_url, test_url, proxy_header, 
                 send_header=None, send_value=None, verbose=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxy_url = proxy_url
        self.test_url = test_url
        self.proxy_header = proxy_header
        self.send_header = send_header
        self.send_value = send_value
        self.verbose = verbose
        self.test_passed = False
        self.header_value = None
        self.error_message = None
    
    def start_requests(self):
        meta = {"proxy": self.proxy_url}
        
        # Add custom proxy headers if specified
        if self.send_header and self.send_value:
            meta["proxy_headers"] = {self.send_header: self.send_value}
        
        yield scrapy.Request(
            url=self.test_url,
            meta=meta,
            callback=self.parse,
            errback=self.handle_error
        )
    
    def parse(self, response):
        # Check for the expected proxy header
        header_value = response.headers.get(self.proxy_header.encode())
        
        if header_value:
            self.test_passed = True
            self.header_value = header_value.decode() if isinstance(header_value, bytes) else header_value
        else:
            self.test_passed = False
            self.error_message = f"Header '{self.proxy_header}' not found in response"
    
    def handle_error(self, failure):
        self.test_passed = False
        self.error_message = str(failure.value)


def run_test(proxy_url: str, test_url: str, proxy_header: str,
             send_header: str = None, send_value: str = None,
             verbose: bool = False) -> bool:
    """
    Run the proxy header test.
    
    Returns True if test passed, False otherwise.
    """
    # Print test configuration
    print("Testing scrapy-proxy-headers")
    print("=" * 28)
    print(f"Proxy URL: {proxy_url}")
    print(f"Test URL: {test_url}")
    print(f"Checking for header: {proxy_header}")
    
    if send_header and send_value:
        print(f"Sending header: {send_header}: {send_value}")
    
    print()
    
    # Create and run the spider
    process = CrawlerProcess(settings={
        "LOG_ENABLED": False,
    })
    
    # Store spider instance to check results
    spider_instance = None
    
    def store_spider(spider):
        nonlocal spider_instance
        spider_instance = spider
    
    crawler = process.create_crawler(ProxyHeaderTestSpider)
    crawler.signals.connect(store_spider, signal=scrapy.signals.spider_opened)
    
    process.crawl(
        crawler,
        proxy_url=proxy_url,
        test_url=test_url,
        proxy_header=proxy_header,
        send_header=send_header,
        send_value=send_value,
        verbose=verbose
    )
    
    process.start()
    
    # Check results
    if spider_instance is None:
        print("[FAIL] Spider did not start")
        return False
    
    if spider_instance.test_passed:
        if verbose and spider_instance.header_value:
            print(f"[PASS] Received header {proxy_header}: {spider_instance.header_value}")
        else:
            print(f"[PASS] Received header {proxy_header}")
        return True
    else:
        print(f"[FAIL] {spider_instance.error_message}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test proxy header functionality with scrapy-proxy-headers"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show header values in output"
    )
    args = parser.parse_args()
    
    # Get configuration from environment
    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTPS_PROXY")
    if not proxy_url:
        print("Error: PROXY_URL or HTTPS_PROXY environment variable required")
        sys.exit(1)
    
    test_url = os.environ.get("TEST_URL", "https://api.ipify.org?format=json")
    proxy_header = os.environ.get("PROXY_HEADER", "X-ProxyMesh-IP")
    send_header = os.environ.get("SEND_PROXY_HEADER")
    send_value = os.environ.get("SEND_PROXY_VALUE")
    
    # Run the test
    success = run_test(
        proxy_url=proxy_url,
        test_url=test_url,
        proxy_header=proxy_header,
        send_header=send_header,
        send_value=send_value,
        verbose=args.verbose
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
