import gzip, sys

from scrapy.downloadermiddlewares.httpcompression import HttpCompressionMiddleware

try:
    import zstd
except ImportError:
    zstd = None


class SafeHttpCompressionMiddleware(HttpCompressionMiddleware):
    """Catch decompress errors — some servers send broken/mismatched bodies."""

    def _decode(self, body, encoding, max_size):
        try:
            return super()._decode(body, encoding, max_size)
        except Exception:
            # Raised when body doesn't match declared encoding (e.g. HTML with gzip header)
            if isinstance(sys.exc_info()[1], gzip.BadGzipFile):
                return body
            if zstd is not None and hasattr(zstd, 'ZstdError') and isinstance(sys.exc_info()[1], zstd.ZstdError):
                return body
            raise


class ProxyMiddleware:
    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_request(self, request):
        if self.settings.getbool("PROXY_ENABLED"):
            request.meta["proxy"] = self.settings.get("PROXY_URL")
