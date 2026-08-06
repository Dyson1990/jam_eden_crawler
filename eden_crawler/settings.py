BOT_NAME = "eden_crawler"
SPIDER_MODULES = ["eden_crawler.spiders"]
NEWSPIDER_MODULE = "eden_crawler.spiders"
ROBOTSTXT_OBEY = False

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": None,
    "eden_crawler.middlewares.UserAgentMiddleware": 50,
    "eden_crawler.middlewares.ProxyMiddleware": 100,
    "eden_crawler.middlewares.Non200Middleware": 200,
    "eden_crawler.middlewares.SafeHttpCompressionMiddleware": 810,
}

ITEM_PIPELINES = {
    "eden_crawler.pipelines.SQLitePipeline": 300,
}

# Local proxy. None=disabled, "clash"/"v2ray"=auto-detect, int=port
PROXY_PORT = None

# None → hyper-h2, "httpx" → httpx, "curl_cffi" → curl_cffi, "playwright" → playwright
HTTP_BACKEND = None

DOWNLOAD_HANDLERS = {
    "http": "eden_crawler.myhandlers.router.RouterDownloadHandler",
    "https": "eden_crawler.myhandlers.router.RouterDownloadHandler",
}

LOG_LEVEL = "INFO"

# When True, save non-200 response bodies to logs/ for debugging
DEV_MODE = True

DOWNLOAD_DELAY = 1
ASSET_DIR = "downloads"
