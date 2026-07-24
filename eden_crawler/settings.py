BOT_NAME = "eden_crawler"
SPIDER_MODULES = ["eden_crawler.spiders"]
NEWSPIDER_MODULE = "eden_crawler.spiders"
ROBOTSTXT_OBEY = False

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": None,
    "eden_crawler.middlewares.SafeHttpCompressionMiddleware": 810,
    "eden_crawler.middlewares.ProxyMiddleware": 100,
}

ITEM_PIPELINES = {
    "eden_crawler.pipelines.SQLitePipeline": 300,
}

PROXY_ENABLED = True
PROXY_URL = "http://127.0.0.1:10808"

# None → hyper-h2, "scrapy" → default, "httpx" → httpx, "curl_cffi" → curl_cffi
HTTP_BACKEND = None

if HTTP_BACKEND == "httpx":
    DOWNLOAD_HANDLERS = {
        "http": "eden_crawler.myhandlers.httpx.HttpxDownloadHandler",
        "https": "eden_crawler.myhandlers.httpx.HttpxDownloadHandler",
    }
elif HTTP_BACKEND == "curl_cffi":
    DOWNLOAD_HANDLERS = {
        "http": "eden_crawler.myhandlers.curl_cffi.CurlCffiDownloadHandler",
        "https": "eden_crawler.myhandlers.curl_cffi.CurlCffiDownloadHandler",
    }
elif HTTP_BACKEND is None:
    DOWNLOAD_HANDLERS = {
        "https": "eden_crawler.myhandlers.http2.H2DownloadHandler",
    }

LOG_LEVEL = "INFO"

# Set True to suppress Scrapy's verbose telemetry/engine output
LOG_QUIET = False

ASSET_DIR = "downloads"
