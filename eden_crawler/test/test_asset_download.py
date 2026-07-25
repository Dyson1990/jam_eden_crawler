"""Integration test: spider → Asset → pipeline download via Scrapy downloader."""
import hashlib
import os
import sys
import tempfile

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from eden_crawler.items import DynamicItem, Asset

TEST_IMG_URL = "https://httpbin.org/image/png"
TEST_DIR = tempfile.mkdtemp(prefix="asset_test_")


class AssetTestSpider(scrapy.Spider):
    name = "asset_test"
    start_urls = ["https://httpbin.org/html"]

    def parse(self, response):
        item = DynamicItem()
        item["name"] = "test_image"
        item["img_file"] = Asset(TEST_IMG_URL, typ="file")
        item["img_blob"] = Asset(TEST_IMG_URL, typ="blob")
        yield item


def run():
    results = []

    def collect(item, **_):
        results.append(item)

    settings = get_project_settings()
    settings.set("ASSET_DIR", TEST_DIR)
    settings.set("LOG_LEVEL", "ERROR")

    process = CrawlerProcess(settings, install_root_handler=False)
    crawler = process.create_crawler(AssetTestSpider)
    crawler.signals.connect(collect, signal=scrapy.signals.item_scraped)
    process.crawl(crawler)
    process.start()

    if not results:
        print("FAIL: no item collected")
        return 1

    item = results[0]

    filepath = item.get("img_file")
    if not filepath or not os.path.exists(filepath):
        print(f"FAIL: file not saved, got: {filepath!r}")
        return 1
    with open(filepath, "rb") as f:
        data = f.read()
    if not data or data[:4] != b"\x89PNG":
        print(f"FAIL: not a valid PNG (starts with {data[:20]!r})")
        return 1
    print(f"OK: file saved → {filepath} ({len(data)} bytes, valid PNG)")

    blob = item.get("img_blob")
    if not isinstance(blob, bytes) or blob[:4] != b"\x89PNG":
        print(f"FAIL: blob not valid PNG (type={type(blob).__name__}, len={len(blob) if blob else 0})")
        return 1
    print(f"OK: blob → {len(blob)} bytes, valid PNG")

    expected_fname = hashlib.md5(TEST_IMG_URL.encode()).hexdigest() + ".png"
    assert expected_fname in filepath, f"filename mismatch: {expected_fname} not in {filepath}"

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
