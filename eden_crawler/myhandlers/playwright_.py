import asyncio
import json as _json
from urllib.parse import urlparse

from scrapy.http import HtmlResponse


class PlaywrightDownloadHandler:
    lazy = False

    def __init__(self, settings):
        self._timeout = settings.getfloat("DOWNLOAD_TIMEOUT", 30)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    async def download_request(self, request):
        return await asyncio.to_thread(self._fetch, request)

    def _fetch(self, request):
        # On Windows, Scrapy/Twisted sets SelectorEventLoopPolicy which can't
        # spawn subprocesses. Restore ProactorEventLoopPolicy in this thread
        # so Playwright can launch Chromium.
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

        from playwright.sync_api import sync_playwright

        proxy = request.meta.get("proxy")
        headers = {k.decode(): v[0].decode() for k, v in request.headers.items()}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx_opts = {}
            if proxy:
                ctx_opts["proxy"] = {"server": proxy}
            context = browser.new_context(**ctx_opts)
            page = context.new_page()

            if request.method == "GET":
                if headers:
                    page.set_extra_http_headers(headers)
                resp = page.goto(
                    request.url,
                    wait_until="domcontentloaded",
                    timeout=self._timeout * 1000,
                )
                body = page.content().encode()
                url = page.url
                status = resp.status if resp else 200
            else:
                # page.goto() always uses GET. Must navigate to origin first —
                # fetch() from about:blank fails on cross-origin requests.
                origin = f"{urlparse(request.url).scheme}://{urlparse(request.url).netloc}"
                page.goto(origin, wait_until="domcontentloaded", timeout=self._timeout * 1000)

                req_body = request.body.decode() if request.body else ""
                result = page.evaluate(
                    """async ([url, method, body, headers]) => {
                        const resp = await fetch(url, {
                            method,
                            headers: JSON.parse(headers),
                            body: body || undefined
                        });
                        return {
                            status: resp.status,
                            body: await resp.text(),
                            url: resp.url
                        };
                    }""",
                    [request.url, request.method, req_body, _json.dumps(headers)],
                )
                status = result["status"]
                body = result["body"].encode()
                url = result["url"]

            browser.close()

        return HtmlResponse(
            url=url,
            status=status,
            body=body,
            request=request,
            encoding="utf-8",
        )

    async def close(self):
        pass
