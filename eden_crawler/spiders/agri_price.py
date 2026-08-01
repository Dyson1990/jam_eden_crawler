import json
import re
import base64

import scrapy
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from eden_crawler.items import DynamicItem


_MAIN_URL = "https://pfsc.agri.cn/"
_API_URL = (
    "https://pfsc.agri.cn/price_portal/index/getMarketReportPriceChart"
    "?marketIDs=&provinceCodes=&varietyID=1383"
)


class AgriPriceSpider(scrapy.Spider):
    name = "agri_price"

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "HTTP_BACKEND": "playwright",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            ),
            "Referer": "https://pfsc.agri.cn/",
            "Origin": "https://pfsc.agri.cn",
        },
    }

    async def start(self):
        yield scrapy.Request(_MAIN_URL, callback=self.find_js)

    def find_js(self, response):
        m = re.search(r'<script[^>]+src="([^"]+app[^"]*\.js)"', response.text)
        if not m:
            self.logger.error("App JS bundle not found")
            return
        js_url = response.urljoin(m.group(1))
        yield scrapy.Request(js_url, callback=self.extract_key)

    def extract_key(self, response):
        m = re.search(r'Utf8\.parse\("([^"]{32})"\)', response.text)
        if not m:
            self.logger.error("AES key not found in JS")
            return
        key = m.group(1).encode("utf-8")
        yield scrapy.Request(
            _API_URL, method="POST",
            callback=self.parse,
            meta={"aes_key": key, "HTTP_BACKEND": "httpx"},
        )

    def parse(self, response):
        key = response.meta["aes_key"]
        raw = json.loads(response.text)
        plain = self._decrypt(raw.get("data"), key)
        if not plain:
            self.logger.error("Decrypt failed")
            return

        data = json.loads(plain)
        date = data.get("date")
        markets = data.get("x", [])
        prices = data.get("y", [])

        for market, price in zip(markets, prices):
            item = DynamicItem()
            item["date"] = date
            item["market"] = market
            item["price"] = price
            item["variety_id"] = "1383"
            yield item

    def _decrypt(self, encrypted, key):
        if not encrypted:
            return None
        iv = encrypted[:16].encode("utf-8")
        ciphertext = base64.b64decode(encrypted[16:])
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        pad_len = plaintext[-1]
        return plaintext[:-pad_len].decode("utf-8")
