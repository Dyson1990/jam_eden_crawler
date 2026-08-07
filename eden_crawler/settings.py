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

# Playwright browser channel. None=bundled chromium, "chrome"=system Chrome
PLAYWRIGHT_CHANNEL = None

DOWNLOAD_HANDLERS = {
    "http": "eden_crawler.myhandlers.router.RouterDownloadHandler",
    "https": "eden_crawler.myhandlers.router.RouterDownloadHandler",
}

LOG_LEVEL = "INFO"

# When True, save non-200 response bodies to logs/ for debugging
DEV_MODE = True

DOWNLOAD_DELAY = 1                     # 同站请求最小间隔（秒）
RANDOMIZE_DOWNLOAD_DELAY = True         # 间隔随机抖动 0.5×~1.5×，避免规律被识别
CONCURRENT_REQUESTS_PER_DOMAIN = 2      # 同域名最大并发请求数
CONCURRENT_REQUESTS_PER_IP = 2          # 同 IP 最大并发请求数
AUTOTHROTTLE_ENABLED = True             # 根据服务器响应时间自动降速
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0   # 目标：同时仅 1 个请求在途

ASSET_DIR = "downloads"
