class RouterDownloadHandler:
    """Route to handler per-request by HTTP_BACKEND in request.meta."""

    lazy = False

    @classmethod
    def from_crawler(cls, crawler):
        from eden_crawler.myhandlers.http2 import H2DownloadHandler
        from eden_crawler.myhandlers.httpx import HttpxDownloadHandler
        from eden_crawler.myhandlers.curl_cffi import CurlCffiDownloadHandler
        from eden_crawler.myhandlers.playwright_ import PlaywrightDownloadHandler

        s = crawler.spider.settings
        return cls(
            fallback=s.get("HTTP_BACKEND"),
            h2=H2DownloadHandler.from_crawler(crawler),
            httpx=HttpxDownloadHandler.from_crawler(crawler),
            curl_cffi=CurlCffiDownloadHandler.from_crawler(crawler),
            playwright=PlaywrightDownloadHandler.from_crawler(crawler),
        )

    def __init__(self, *, fallback, h2, httpx, curl_cffi, playwright):
        self._fallback = fallback
        self._handlers = {
            None: h2,
            "httpx": httpx,
            "curl_cffi": curl_cffi,
            "playwright": playwright,
        }

    def _resolve(self, request):
        # priority: request.meta > spider custom_settings > settings.py
        backend = request.meta.get("HTTP_BACKEND", self._fallback)
        return self._handlers.get(backend, self._handlers[None])

    async def download_request(self, request):
        return await self._resolve(request).download_request(request)

    async def close(self):
        for h in self._handlers.values():
            await h.close()
