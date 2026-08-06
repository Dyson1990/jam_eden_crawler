import gzip
import socket
import sys

from scrapy.downloadermiddlewares.httpcompression import HttpCompressionMiddleware

try:
    import zstd
except ImportError:
    zstd = None


class SafeHttpCompressionMiddleware(HttpCompressionMiddleware):
    """Catch decompress errors on broken/mismatched Content-Encoding."""

    def _decode(self, body, encoding, max_size):
        try:
            return super()._decode(body, encoding, max_size)
        except Exception:
            exc = sys.exc_info()[1]
            if isinstance(exc, gzip.BadGzipFile):
                return body
            if zstd is not None and hasattr(zstd, "ZstdError") and isinstance(
                    exc, zstd.ZstdError):
                return body
            raise


class ProxyMiddleware:
    """Set proxy from PROXY_PORT setting. Supports keyword auto-detection."""

    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_request(self, request):
        port = self.settings.get("PROXY_PORT")
        if port is None:
            return
        port = self._resolve(port)
        if port:
            request.meta["proxy"] = f"http://127.0.0.1:{port}"

    def _resolve(self, port):
        if isinstance(port, int):
            return port if self._check(port) else None
        return self._detect(port)

    @staticmethod
    def _check(port):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            s.close()
            return True
        except OSError:
            return False

    @classmethod
    def _detect(cls, keyword):
        port_map = {
            "clash": [7890, 7891],
            "v2ray": [10808, 10809],
        }
        ports = port_map.get(keyword.lower(), [
            7890, 10808, 10809, 7891, 8118, 8888,
        ])
        for p in ports:
            if cls._check(p):
                return p
        return None


class Non200Middleware:
    """Log non-200 as ERROR. Save body when DEV_MODE or non-200."""

    def __init__(self, dev_mode):
        self._dev_mode = dev_mode

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.getbool("DEV_MODE", False))

    def process_response(self, request, response, spider):
        if response.status != 200:
            spider.logger.error("Non-200: %s → %s", request.url, response.status)

        if self._dev_mode or response.status != 200:
            from eden_crawler.log import save_body
            save_body(spider.name, request.url, response.body)

        return response

    def process_exception(self, request, exception, spider):
        spider.logger.error("Request failed: %s → %s", request.url, exception)


class UserAgentMiddleware:
    """Set random User-Agent via anti_useragent if none set by spider."""

    def __init__(self):
        from anti_useragent import UserAgent
        self._ua = UserAgent()

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        if "User-Agent" not in request.headers:
            request.headers["User-Agent"] = self._ua.random
