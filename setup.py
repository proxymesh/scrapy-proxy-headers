from setuptools import setup, find_packages

setup(
    name="scrapy_proxy_headers",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "scrapy>=2.0",
    ],
    entry_points={
        "scrapy.downloader_handlers": [
            "https = scrapy_proxy_headers.HTTP11ProxyDownloadHandler"
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        #"License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
