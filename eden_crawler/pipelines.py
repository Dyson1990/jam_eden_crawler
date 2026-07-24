import hashlib
import logging
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import scrapy
from twisted.internet import defer

from eden_crawler.items import Asset


class SQLitePipeline:
    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        o._crawler = crawler
        return o

    def open_spider(self):
        spider = self._crawler.spider
        if spider.settings.getbool("LOG_QUIET", False):
            logging.getLogger("scrapy").setLevel(logging.WARNING)
        self.conn = sqlite3.connect("data.db")
        self.cursor = self.conn.cursor()
        spider_file = spider.__class__.__module__.split(".")[-1]
        self.table_name = f"spider_{spider_file}"
        self._asset_dir = spider.settings.get("ASSET_DIR", "downloads")

    def close_spider(self):
        self.conn.close()

    def _ensure_table(self, fields):
        column_defs = ["insert_time TEXT"] + [f"{f} TEXT" for f in fields]
        self.cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(column_defs)})"
        )
        self.conn.commit()

    def _sync_columns(self, fields):
        self.cursor.execute(f"PRAGMA table_info({self.table_name})")
        existing = {row[1] for row in self.cursor.fetchall()}
        for f in fields:
            if f not in existing:
                self.cursor.execute(
                    f"ALTER TABLE {self.table_name} ADD COLUMN {f} TEXT"
                )
        self.conn.commit()

    def _guess_ext(self, content_type, url):
        ct = (content_type or "").lower()
        for prefix, ext in [
            ("image/jpeg", ".jpg"), ("image/jpg", ".jpg"),
            ("image/png", ".png"), ("image/gif", ".gif"),
            ("image/webp", ".webp"), ("video/mp4", ".mp4"),
            ("video/webm", ".webm"),
        ]:
            if prefix in ct:
                return ext
        _, ext = os.path.splitext(urlparse(url).path)
        return ext or ""

    @defer.inlineCallbacks
    def _download_assets(self, item):
        """Download all Asset values via Scrapy's downloader, replace in-place."""
        pairs = []  # (key, Asset, Deferred)

        for key in list(item.keys()):
            val = item.get(key)
            if not isinstance(val, Asset):
                continue
            headers = {"Referer": val.referer} if val.referer else None
            request = scrapy.Request(val.url, method="GET", headers=headers,
                                     dont_filter=True)
            pairs.append((key, val, self._crawler.engine.download(request)))

        if not pairs:
            return item

        results = yield defer.DeferredList(
            [d for _, _, d in pairs], consumeErrors=True)

        for (key, val, _), (ok, response) in zip(pairs, results):
            if not ok:
                item[key] = None
                continue
            try:
                if val.type == "file":
                    dir_path = os.path.join(self._asset_dir, self.table_name)
                    os.makedirs(dir_path, exist_ok=True)
                    ct = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore")
                    ext = self._guess_ext(ct, val.url)
                    fname = hashlib.md5(val.url.encode()).hexdigest() + ext
                    filepath = os.path.join(dir_path, fname)
                    if not os.path.exists(filepath):
                        with open(filepath, "wb") as f:
                            f.write(response.body)
                    item[key] = filepath
                else:
                    item[key] = response.body
            except Exception:
                item[key] = None

        return item

    @defer.inlineCallbacks
    def process_item(self, item):
        item = yield self._download_assets(item)

        fields = list(item.fields.keys())
        self._ensure_table(fields)
        self._sync_columns(fields)

        values = [datetime.now().isoformat()]
        values += [
            datetime.now().isoformat() if f == "timestamp" and not item.get(f) else item.get(f)
            for f in fields
        ]
        placeholders = ", ".join(["?"] * (len(fields) + 1))
        self.cursor.execute(
            f"INSERT INTO {self.table_name} (insert_time, {', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        self.conn.commit()
        return item
