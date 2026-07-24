import hashlib
import logging
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

import httpx

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
        """Create table on first item if not exists."""
        column_defs = ["insert_time TEXT"] + [f"{f} TEXT" for f in fields]
        self.cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {', '.join(column_defs)})"
        )
        self.conn.commit()

    def _sync_columns(self, fields):
        """Add new columns that appear in later items."""
        self.cursor.execute(f"PRAGMA table_info({self.table_name})")
        existing = {row[1] for row in self.cursor.fetchall()}
        for f in fields:
            if f not in existing:
                self.cursor.execute(
                    f"ALTER TABLE {self.table_name} ADD COLUMN {f} TEXT"
                )
        self.conn.commit()

    def _guess_ext(self, content_type, url):
        """Infer file extension from Content-Type or URL path."""
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

    def _process_assets(self, item):
        """Download Asset values and replace in-place."""
        for key in list(item.keys()):
            val = item.get(key)
            if not isinstance(val, Asset):
                continue
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                }
                if val.referer:
                    headers["Referer"] = val.referer
                resp = httpx.get(val.url, headers=headers, follow_redirects=True)
                resp.raise_for_status()
                if val.type == "file":
                    dir_path = os.path.join(self._asset_dir, self.table_name)
                    os.makedirs(dir_path, exist_ok=True)
                    ext = self._guess_ext(resp.headers.get("content-type"), val.url)
                    fname = hashlib.md5(val.url.encode()).hexdigest() + ext
                    filepath = os.path.join(dir_path, fname)
                    if not os.path.exists(filepath):
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                    item[key] = filepath
                else:
                    item[key] = resp.content
            except Exception:
                item[key] = None

    def process_item(self, item):
        self._process_assets(item)

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
