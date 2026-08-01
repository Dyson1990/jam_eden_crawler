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

# Local proxy port. None to disable.
# PROXY_PORT = 10808
PROXY_PORT = None

# None → hyper-h2, "httpx" → httpx, "curl_cffi" → curl_cffi, "playwright" → playwright
# Per-spider override: set custom_settings = {"HTTP_BACKEND": "playwright"} in your spider
HTTP_BACKEND = None

DOWNLOAD_HANDLERS = {
    "http": "eden_crawler.myhandlers.router.RouterDownloadHandler",
    "https": "eden_crawler.myhandlers.router.RouterDownloadHandler",
}

LOG_LEVEL = "INFO"

# Set True to suppress Scrapy's verbose telemetry/engine output
LOG_QUIET = False

ASSET_DIR = "downloads"
