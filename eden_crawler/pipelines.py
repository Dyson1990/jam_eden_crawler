import asyncio
import hashlib
import logging
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import scrapy

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
        self._asset_dir = os.path.abspath(
            spider.settings.get("ASSET_DIR", "downloads"))

    def close_spider(self):
        self.conn.close()

    def _ensure_table(self, fields, blob_fields):
        col_types = []
        for f in fields:
            col_types.append(f"{f} BLOB" if f in blob_fields else f"{f} TEXT")
        column_defs = ["insert_time TEXT"] + col_types
        self.cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} "
            f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(column_defs)})"
        )
        self.conn.commit()

    def _sync_columns(self, fields, blob_fields):
        self.cursor.execute(f"PRAGMA table_info({self.table_name})")
        existing = {row[1] for row in self.cursor.fetchall()}
        for f in fields:
            if f not in existing:
                col_type = "BLOB" if f in blob_fields else "TEXT"
                self.cursor.execute(
                    f"ALTER TABLE {self.table_name} ADD COLUMN {f} {col_type}"
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

    async def _download_assets(self, item):
        """Download all Asset values via Scrapy's downloader, replace in-place."""
        keys, assets, tasks = [], [], []

        for key in list(item.keys()):
            val = item.get(key)
            if not isinstance(val, Asset):
                continue
            keys.append(key)
            assets.append(val)
            url = val.url
            if url.startswith("//"):
                url = "https:" + url
            headers = {"Referer": val.referer} if val.referer else None
            request = scrapy.Request(url, method="GET", headers=headers,
                                     dont_filter=True)
            tasks.append(self._crawler.engine.download_async(request))

        if not tasks:
            return item

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for key, val, result in zip(keys, assets, results):
            if isinstance(result, Exception):
                item[key] = None
                continue
            try:
                response = result
                if val.typ == "file":
                    dir_path = os.path.join(self._asset_dir, self.table_name)
                    os.makedirs(dir_path, exist_ok=True)
                    ct = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore")
                    ext = self._guess_ext(ct, val.url)
                    fname = hashlib.md5(val.url.encode()).hexdigest() + ext
                    filepath = os.path.abspath(os.path.join(dir_path, fname))
                    if not os.path.exists(filepath):
                        with open(filepath, "wb") as f:
                            f.write(response.body)
                    item[key] = filepath
                else:
                    item[key] = response.body
            except Exception:
                item[key] = None

        return item

    async def process_item(self, item):
        item = await self._download_assets(item)

        fields = list(item.fields.keys())
        # Fields whose value is bytes → BLOB column
        blob_fields = {f for f in fields if isinstance(item.get(f), bytes)}
        self._ensure_table(fields, blob_fields)
        self._sync_columns(fields, blob_fields)

        values = [datetime.now().isoformat()]
        for f in fields:
            v = item.get(f)
            if f == "timestamp" and not v:
                values.append(datetime.now().isoformat())
            elif isinstance(v, bytes):
                values.append(sqlite3.Binary(v))
            else:
                values.append(v)
        placeholders = ", ".join(["?"] * (len(fields) + 1))
        self.cursor.execute(
            f"INSERT INTO {self.table_name} (insert_time, {', '.join(fields)}) VALUES ({placeholders})",
            values,
        )
        self.conn.commit()
        return item
