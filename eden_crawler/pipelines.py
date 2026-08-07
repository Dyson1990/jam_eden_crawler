import asyncio
import hashlib
import os
from datetime import datetime
from urllib.parse import urlparse

import scrapy
from sqlalchemy import (
    Column,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)

from eden_crawler.items import Asset
from eden_crawler.log import setup_logging


class SQLitePipeline:
    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        o._crawler = crawler
        return o

    def open_spider(self):
        spider = self._crawler.spider
        setup_logging(spider)
        self._log = spider.logger

        self._engine = create_engine(f"sqlite:///{os.path.abspath('data.db')}")
        self._metadata = MetaData()

        spider_file = spider.__class__.__module__.split(".")[-1]
        self._base_table = f"spider_{spider_file}"
        self._asset_dir = os.path.abspath(
            spider.settings.get("ASSET_DIR", "downloads"))

    def close_spider(self):
        self._engine.dispose()

    # -- Table helpers --

    def _table_name(self, item):
        tbl = item.get("_dbt")
        return f"{self._base_table}_{tbl}" if tbl else self._base_table

    def _get_table(self, table_name):
        """Return Table object, reflecting from DB if needed."""
        tbl = self._metadata.tables.get(table_name)
        if tbl is not None:
            return tbl
        return Table(table_name, self._metadata, autoload_with=self._engine)

    def _ensure_table(self, table_name, fields, blob_fields):
        """Create table if not exists."""
        if inspect(self._engine).has_table(table_name):
            return
        cols = [
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("insert_time", Text),
        ]
        for f in fields:
            cols.append(
                Column(f, LargeBinary if f in blob_fields else Text))
        Table(table_name, self._metadata, *cols)
        self._metadata.create_all(self._engine)

    def _sync_columns(self, table_name, fields, blob_fields):
        """Add missing columns to existing table."""
        insp = inspect(self._engine)
        existing = {c["name"] for c in insp.get_columns(table_name)}
        added = False
        with self._engine.connect() as conn:
            for f in fields:
                if f not in existing:
                    col_type = "BLOB" if f in blob_fields else "TEXT"
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {f} {col_type}"))
                    added = True
            if added:
                conn.commit()
        return added


    # -- Download helpers --

    @staticmethod
    def _guess_ext(content_type, url):
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

    @staticmethod
    def _extract_fname(url):
        """Extract filename from URL path, fallback to md5 hash."""
        path = urlparse(url).path
        fname = os.path.basename(path)
        if fname and "." in fname:
            return fname
        return None

    def _resolve_path(self, dir_path, fname):
        """Resolve file path. If fname exists, insert timestamp before ext."""
        filepath = os.path.abspath(os.path.join(dir_path, fname))
        if os.path.exists(filepath):
            base, ext = os.path.splitext(fname)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")  # noqa: DTZ005
            filepath = os.path.abspath(
                os.path.join(dir_path, f"{base}_{ts}{ext}"))
        return filepath

    async def _download_assets(self, item):
        """Download Asset values via Scrapy downloader, replace in-place."""
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
            request = scrapy.Request(
                url, method="GET", headers=headers, dont_filter=True)
            tasks.append(self._crawler.engine.download_async(request))

        if not tasks:
            return item

        total = len(tasks)
        self._log.debug("downloading %d asset(s)", total)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (key, val, result) in enumerate(
            zip(keys, assets, results), 1
        ):
            if isinstance(result, Exception):
                self._log.debug("[%d/%d] FAIL %s", i, total, val.url)
                item[key] = None
                continue
            try:
                response = result
                if val.typ == "file":
                    dir_path = os.path.join(
                        self._asset_dir, self._table_name(item))
                    os.makedirs(dir_path, exist_ok=True)
                    ct = response.headers.get(
                        "Content-Type", b"").decode("utf-8", errors="ignore")
                    ext = self._guess_ext(ct, val.url)

                    # Determine filename: fn > URL basename > md5 hash
                    if val.fn:
                        fname = val.fn
                    else:
                        fname = self._extract_fname(val.url)
                        if fname is None:
                            fname = hashlib.md5(
                                val.url.encode()).hexdigest()[:8] + ext
                        elif not fname.endswith(ext):
                            fname = (
                                os.path.splitext(fname)[0] + ext
                                if ext else fname)

                    filepath = self._resolve_path(dir_path, fname)
                    with open(filepath, "wb") as f:  # noqa: ASYNC230
                        f.write(response.body)
                    item[key] = filepath
                    self._log.debug("[%d/%d] %s → %s", i, total,
                                    os.path.basename(filepath))
                else:
                    item[key] = response.body
                    self._log.debug("[%d/%d] %s → blob(%d B)", i, total,
                                    val.url, len(response.body))
            except Exception:  # noqa: BLE001
                self._log.debug("[%d/%d] FAIL %s", i, total, val.url)
                item[key] = None

        return item

    async def process_item(self, item):
        item = await self._download_assets(item)

        table = self._table_name(item)
        fields = [f for f in item.fields
                  if f != "_dbt"]
        blob_fields = {f for f in fields if isinstance(item.get(f), bytes)}

        self._ensure_table(table, fields, blob_fields)
        self._sync_columns(table, fields, blob_fields)

        values = {"insert_time": datetime.now().isoformat()}  # noqa: DTZ005
        for f in fields:
            v = item.get(f)
            if f == "timestamp" and not v:
                values[f] = datetime.now().isoformat()  # noqa: DTZ005
            else:
                values[f] = v

        tbl = self._get_table(table)
        with self._engine.connect() as conn:
            conn.execute(tbl.insert().values(**values))
            conn.commit()

        return item
