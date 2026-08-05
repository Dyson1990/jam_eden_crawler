---
name: new-spider
description: |
  Create a new Scrapy spider for the Eden Crawler project. Use this skill whenever
  the user asks to build a crawler, spider, scraper, or to crawl/scrape a website,
  collect data from a site, or extract structured data from web pages. Also trigger
  when the user mentions writing a spider, 爬虫, or 爬取.

  The skill enforces project conventions:
  - Spider files go in `eden_crawler/spiders/` (Scrapy-style)
  - Always use `DynamicItem` instead of pre-defining fields
  - Use `Asset(url, typ="blob")` to mark images/files for auto-download
  - HTTP non-200: ask user for headers before trying other workarounds
  - No package installation unless the user explicitly asks
---

# Eden Crawler — New Spider

## Before writing

1. Ask the user **what website** they want to crawl and **what data** they want extracted (fields, depth, pagination).
2. With that info, create a `.py` file in `eden_crawler/spiders/`.

## Spider file template

Every spider follows this skeleton:

```python
import json
import scrapy
from eden_crawler.items import DynamicItem, Asset


class <Name>Spider(scrapy.Spider):
    name = "<name>"

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        # "USER_AGENT": "...",       # 如果网站有反爬虫措施，由用户提供
        # "DEFAULT_REQUEST_HEADERS": { ... },  # 如果网站要求认证，由用户提供
    }

    # 方式 A: 固定起始 URL
    start_urls = ["<target_url>"]

    # 方式 B: 动态起始（比如需要拼接 URL）
    # async def start(self):
    #     yield scrapy.Request("<target_url>", callback=self.parse)

    def parse(self, response):
        ...
```

## File-name & class-name conventions

- File name = `name` value = lowercase/camelCase like `ip`, `car`, `news_list`
- Class name = PascalCase + `Spider` suffix, e.g. `IpSpider`, `CarSpider`, `NewsListSpider`

## Items — always use `DynamicItem`

```python
item = DynamicItem()
item["title"] = title
item["price"] = price
item["url"] = response.url
yield item
```

Fields auto-register on first assignment — never pre-define them in a separate Item class.

## Assets (images/files)

Wrap URLs with `Asset` so the download pipeline handles them:

```python
from eden_crawler.items import Asset

item["cover"] = Asset(cover_url, typ="blob")   # blob → binary in DB
item["file"]  = Asset(file_url,  typ="file")   # file → local path

# 图片列表
item["images"] = json.dumps([img for img in image_urls][:5], ensure_ascii=False)
```

If the site blocks image requests, add `referer`:

```python
item["cover"] = Asset(cover_url, typ="blob", referer=response.url)
```

## Multi-level crawling

Use `response.meta` to carry context between levels. Example pattern (like `car.py`):

```python
def parse(self, response):
    # level-1 list
    for item in items:
        yield item
        yield scrapy.Request(detail_url, callback=self.parse_detail,
                             meta={"parent_name": item["name"]})

def parse_detail(self, response):
    parent = response.meta["parent_name"]
    ...
```

## Dedup

Use `self.seen_*` sets to skip duplicates when the listing page has no pagination API:

```python
def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.seen_urls = set()
```

## XPath helpers (from `car.py`)

```python
def _make_url(self, raw, response):
    """Return absolute http URL, or None for invalid/dummy links."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("javascript:") or raw == "#" or raw.startswith("void"):
        return None
    if raw.startswith("http"):
        return raw
    if raw.startswith("//"):
        return "https:" + raw
    return response.urljoin(raw)
```

Multi-fallback XPath extraction pattern:

```python
text = (
    node.xpath('normalize-space(.//*[contains(@class, "target")])').get('') or
    node.xpath('normalize-space(.//h3)').get('') or
    node.xpath('normalize-space(.//a)').get('')
).strip()
```

## Rules

1. **No package installation** unless the user explicitly asks. Use only `scrapy`, `json` (stdlib), and `eden_crawler.items`.

2. **HTTP non-200** — if the target site returns any status other than 200 (403, 404, 500, etc.):
   - **First action**: stop and ask the user to provide headers (User-Agent, Cookie, Referer, Authorization). Do NOT try workarounds (proxies, delays, random UA generators) before asking.
   - Once the user provides headers, inject them via `custom_settings["DEFAULT_REQUEST_HEADERS"]` or per-Request `headers=` kwarg.
   - Only if the user explicitly says headers won't help, try alternative approaches (scrape through Google cache, use a different source, etc.).

3. **Headless browser** is NOT needed unless the user asks. Default to plain HTTP requests.

4. **Output file format** — yield `DynamicItem` instances; the pipeline handles serialization.

5. Don't traverse the entire project. Only reference `eden_crawler/spiders/` for examples and `eden_crawler/items.py` for `DynamicItem` / `Asset`.
