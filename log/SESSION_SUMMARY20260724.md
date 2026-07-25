# Session 总结 — AI_proj_eden_crawler

## 1. 项目/任务概述

基于 Scrapy 的通用爬虫框架项目，以本地代理为前提运行。核心目标：

- 提供一个可复用的爬虫基础设施：动态 Item、自动建表入库、Asset 下载管线、多 HTTP 后端切换
- Spider 开发者只需关注提取逻辑，不需要手动定义 Item 字段、建表、处理文件下载

## 2. 项目结构

```
AI_proj_eden_crawler/
├── scrapy.cfg
├── data.db                          # SQLite 数据库（自动生成）
├── README.md
├── session_changes.md               # 另一 session 的变更记录
├── .venv/                           # Python 3.14 虚拟环境
├── eden_crawler/
│   ├── __init__.py
│   ├── settings.py                  # 全局配置
│   ├── items.py                     # Asset + DynamicItem
│   ├── pipelines.py                 # SQLitePipeline（建表/Asset下载/入库）
│   ├── middlewares.py               # SafeHttpCompressionMiddleware + ProxyMiddleware
│   ├── myhandlers/
│   │   ├── __init__.py
│   │   ├── http2.py                 # H2 下载处理器（HTTP/2）
│   │   ├── httpx.py                 # httpx 下载处理器
│   │   └── curl_cffi.py             # curl_cffi 下载处理器（TLS 指纹伪装）
│   ├── spiders/
│   │   ├── __init__.py
│   │   ├── ip.py                    # IP 检测测试蜘蛛
│   │   └── car.py                   # 汽车网站爬虫示例（3 级目录）
│   └── test/
│       ├── test_asset_download.py   # Asset 下载集成测试
│       └── qbittorrent.py           # qBittorrent 磁力链接工具
```

## 3. 已完成的关键变更

### 3.1 下载处理器（`myhandlers/`）

**三个自定义 HTTP 后端**，通过 `settings.py` 的 `HTTP_BACKEND` 切换：

| 值 | 处理器 | 特点 |
|---|---|---|
| `None` | `H2DownloadHandler` (http2.py) | 仅 https，HTTP/2 直连，支持代理 CONNECT 隧道 |
| `"httpx"` | `HttpxDownloadHandler` (httpx.py) | http + https，走 httpx 库 |
| `"curl_cffi"` | `CurlCffiDownloadHandler` (curl_cffi.py) | http + https，TLS 指纹伪装 chrome110 |

**共同设计决策：**
- 每个 handler 都有 `from_crawler(cls, crawler)` 类方法，Scrapy 通过此方法实例化（不以 `settings` 为位置参数直接调用 `__init__`）
- `lazy = False`：Scrapy 2.x 要求明确声明
- `download_request` 是 `async def`，内部用 `asyncio.to_thread()` 将同步 `_fetch` 放到线程池避免阻塞事件循环
- `close` 是 `async def`
- 无需 `spider` 参数（Scrapy 2.x 已弃用）

**H2 处理器特殊逻辑 (`http2.py`)：**
- `_tunnel_proxy(host, port, proxy_url, timeout)`：自行创建到代理的 socket，CONNECT 建立隧道后返回；返回的 socket 后续做 SSL 包装
- HTTP/2 状态码从 response headers 的 `:status` 伪头提取（`ResponseReceived` 无 `.status` 属性）

### 3.2 动态 Item 系统 (`items.py`)

```python
class Asset:
    """标记需要下载的 URL。typ='file' → 本地路径，typ='blob' → 数据库二进制"""
    def __init__(self, url, typ="blob", referer=None):
        self.url = url
        self.typ = typ            # 注意：typ 而非 type，避免遮蔽 Python builtin
        self.referer = referer    # 下载时作为 Referer header 发送

class DynamicItem(scrapy.Item):
    """字段自动注册，无需预定义"""
    def __setitem__(self, key, value):
        if key not in self.fields:
            self.fields[key] = scrapy.Field()
        super().__setitem__(key, value)
```

### 3.3 管线 (`pipelines.py`)

**SQLitePipeline 核心能力：**

1. **自动建表**：首次 item 到达时 `CREATE TABLE IF NOT EXISTS`，表名 = `spider_{文件名}`
2. **自动加列**：后续 item 出现新字段时 `ALTER TABLE ADD COLUMN`
3. **BLOB 列自动识别**：字段值是 `bytes` → 列类型 `BLOB`，否则 `TEXT`
4. **二进制包装**：`bytes` 值写入时用 `sqlite3.Binary(v)` 包装
5. **Asset 下载**：`_download_assets()` 遍历 item 字段，`isinstance(value, Asset)` 的字段通过 Scrapy 下载器下载

**`_download_assets` 详细流程：**
```python
async def _download_assets(self, item):
    # 1. 收集所有 Asset 字段
    # 2. 协议相对 URL "//host/path" 补 "https:" 前缀
    # 3. 通过 self._crawler.engine.download_async() 走 Scrapy 下载器链
    #    （代理、中间件、header 注入等全链路）
    # 4. asyncio.gather(*tasks) 并发下载所有 Asset
    # 5. typ="file"：hash URL 取文件名 + Content-Type 推断扩展名 → 写入磁盘
    #    → item[key] = os.path.abspath(文件路径)
    # 6. typ="blob"：item[key] = response.body（bytes）
    # 7. 下载失败 → item[key] = None
```

**架构要点：**
- `process_item` 是 `async def`（Scrapy 2.x 管线的异步接口）
- 建表/加列在 `_download_assets` 之后，确保下载完成后的字段结构和类型都已确定
- `_ensure_table` 和 `_sync_columns` 接收 `blob_fields` 参数用于列类型决策

### 3.4 中间件 (`middlewares.py`)

**SafeHttpCompressionMiddleware：**
- 替换 Scrapy 默认解压中间件
- 只捕获 `gzip.BadGzipFile` 和 `zstd.ZstdError`（不再通配 `Exception`）
- `zstd` 包可能无 `ZstdError`，加了 `hasattr` 守卫

**ProxyMiddleware：**
- 已适配 Scrapy 2.x：`__init__(self, settings)` + `from_crawler(cls, crawler)`
- `process_request(self, request)` 无需 `spider` 参数

### 3.5 配置 (`settings.py`)

```python
PROXY_ENABLED = True
PROXY_URL = "http://127.0.0.1:10808"
HTTP_BACKEND = None           # 默认 h2
ASSET_DIR = "downloads"       # Asset typ="file" 的文件存储目录
LOG_QUIET = False            # True 时 pipeline 将 scrapy logger 降为 WARNING
LOG_LEVEL = "INFO"
```

### 3.6 Spider 适配

**ip.py** — IP 检测测试：
```python
class IpSpider(scrapy.Spider):
    name = "ip"
    async def start(self):
        yield scrapy.Request("http://ip-api.com/json", callback=self.parse)
    def parse(self, response):
        data = json.loads(response.text)
        item = DynamicItem()
        item["ip"] = data.get("query")
        item["country"] = data.get("country")
        # ... 无需预定义字段，自动入库
        yield item
```

**car.py** — 汽车网站 3 级目录示例：
```python
class CarSpider(scrapy.Spider):
    name = 'car'
    start_urls = ['https://www.autohome.com.cn/car/']

    def _make_url(self, raw, response):
        """过滤 javascript:void(0)、# 等无效链接，补全相对 URL"""
        if not raw: return None
        raw = raw.strip()
        if raw.startswith("javascript:") or raw == "#" or raw.startswith("void"):
            return None
        if raw.startswith("http"): return raw
        if raw.startswith("//"): return "https:" + raw
        return response.urljoin(raw)

    def parse(self, response):      # 品牌列表 → level1 item + 车系请求
    def parse_series(self, response): # 车系列表 → level2 item + 详情请求
    def parse_detail(self, response): # 车型详情 → 详情 item
```

- 品牌 Logo、车系图片、车型图片用 `Asset(url, typ="blob")` 下载
- 多层 JSON 数据（specs/meta）用 `json.dumps()` 序列化存入 TEXT 列

### 3.7 新增工具文件

**`test/qbittorrent.py`** — 发送磁力链接到 qBittorrent Web UI：
```python
def add_magnet(magnet_url, host="http://127.0.0.1:8080",
               username="admin", password="adminadmin"):
    with httpx.Client() as client:
        client.post(f"{host}/api/v2/auth/login", data=...)
        resp = client.post(f"{host}/api/v2/torrents/add", data={"urls": magnet_url})
        return resp.status_code == 200
```

**`test/test_asset_download.py`** — Asset 下载集成测试：
- 创建临时 spider → `CrawlerProcess` 运行
- 验证 `typ="file"` 文件落盘且为有效 PNG
- 验证 `typ="blob"` 返回 bytes 且为有效 PNG
- 验证文件名使用 `md5(url).hexdigest() + ext` 格式

## 4. 代码状态摘要

| 文件 | 状态 | 说明 |
|---|---|---|
| `items.py` | ✅ 完成 | `Asset` + `DynamicItem` |
| `pipelines.py` | ✅ 完成 | 异步 Asset 下载 + 自动建表/BLOB识别 |
| `middlewares.py` | ✅ 完成 | 安全解压 + 代理 |
| `settings.py` | ✅ 完成 | 三后端切换 + ASSET_DIR + LOG_QUIET |
| `myhandlers/http2.py` | ✅ 完成 | H2 + 代理隧道 |
| `myhandlers/httpx.py` | ✅ 完成 | httpx 后端 |
| `myhandlers/curl_cffi.py` | ✅ 完成 | curl_cffi 后端 |
| `spiders/ip.py` | ✅ 完成 | 测试蜘蛛 |
| `spiders/car.py` | ✅ 完成 | 3 级目录示例，`_make_url` 过滤无效链接 |
| `test/test_asset_download.py` | ✅ 完成 | 集成测试 |
| `test/qbittorrent.py` | ✅ 完成 | qBittorrent 工具 |
| `session_changes.md` | 📋 参考 | 另一 session 的变更说明 |

## 5. 待解决问题 / TODO

- **系统 Python 环境变化**：外部 Python 从 3.12 升级到 3.14，需使用 `.venv` 进行所有操作（`./.venv/Scripts/python`、`./.venv/Scripts/scrapy`）
- **`ssl.SSLError`**：部分站点 SSL 连接可能出错（全局代理环境下的常见问题），Handler 未做重试或 fallback 处理
- **`car.py` 为示例爬虫**：目标网站 `autohome.com.cn` 实际 HTML 结构可能与 XPath 不匹配，需按实际页面调整
- **错误重试**：Asset 下载失败目前静默设 `None`，无重试机制
- **代理失效处理**：代理不可用时无 fallback

## 6. 环境与技术栈

| 项 | 值 |
|---|---|
| 运行目录 | `C:\Users\Dyson\Desktop\claude_proj\AI_proj_eden_crawler` |
| Python | 3.14.6（`.venv` 虚拟环境） |
| Scrapy | 2.17.0 |
| httpx | 0.28.1 |
| h2 | 4.3.0 |
| curl_cffi | 0.15.0 |
| 数据库 | SQLite（项目根目录 `data.db`） |
| 操作系统 | Windows 11 Enterprise 10.0.26200 |
| Shell | bash（Git Bash） |

**运行命令：**
```bash
cd "C:\Users\Dyson\Desktop\claude_proj\AI_proj_eden_crawler"
.venv/Scripts/scrapy.exe crawl ip     # 测试蜘蛛
.venv/Scripts/scrapy.exe crawl car    # 汽车蜘蛛
.venv/Scripts/python.exe eden_crawler/test/test_asset_download.py  # 运行测试
```

## 7. 关键决策与约定

| 决策 | 说明 |
|---|---|
| `typ` 而非 `type` | 避免遮蔽 Python builtin `type()` |
| Asset 下载走 Scrapy 下载器 | `engine.download_async()` 而非直接 httpx，确保经过代理、中间件、header 注入全链路 |
| `asyncio.to_thread` | Handler 的 `download_request` 用此方式将同步 `_fetch` 放到线程池 |
| Item 字段自动注册 | `DynamicItem.__setitem__` 覆盖实现，不在 `items.py` 预定义字段 |
| 表名命名 | `spider_{文件名}`，如 `ip.py` → `spider_ip` |
| BLOB 列识别 | Pipeline 中 `isinstance(value, bytes)` → BLOB 列，否则 TEXT |
| `_make_url` | spider 层处理无效 URL（`javascript:`、`#`），返回 `None` |
| `scrapy.Request` vs `yield` | spider 用同步 `parse` + `yield`（不是 `async for`），Handler 内部用 `asyncio.to_thread` |
| 无 spider 参数 | `process_request(request)`、`process_item(item)` 等都不再传 `spider`（Scrapy 2.x 已弃用） |

## 8. 两个 Session 的变更对比

### Session 1（本次 session — 基础架构）

- 三个 handler 加 `from_crawler` 修复 `TypeError: missing 'settings'` 原始 bug
- Handler 方法签名升级：`download_request` async、`close` async、移除 `spider` 参数
- 代理隧道 socket 修复
- `DynamicItem` 字段自动注册
- Pipeline 自动建表/加列
- `ProxyMiddleware` / `SQLitePipeline` 适配 Scrapy 2.x（`from_crawler` + 移除 spider 参数）
- `car.py` 从外部项目迁移适配，`_make_url` 修复 `javascript:void(0)` 崩溃

### Session 2（session_changes.md — Asset 下载管线）

- `Asset` 类：`type` → `typ`，新增 `referer`、`__repr__`
- 下载方式：`httpx` → Scrapy `engine.download_async()`（走下载器链）
- 异步模型：`@defer.inlineCallbacks` → `async def` + `asyncio.gather()`
- 文件存储路径改为 `os.path.abspath` 绝对路径
- BLOB 值用 `sqlite3.Binary()` 包装
- BLOB 列自动识别（`isinstance(v, bytes)`）
- `_guess_ext` 从 Content-Type 推断扩展名
- 协议相对 URL `//host/path` 补 `https:` 前缀
- `SafeHttpCompressionMiddleware` 精确捕获异常类型（不泛化 `Exception`）
- `LOG_QUIET` 静默模式
- 新增 `test/test_asset_download.py` 集成测试
- 新增 `test/qbittorrent.py` 磁力链接工具

---

> 本文件写入于 2026-07-24. 两个 session 的代码已合并到当前工作树。
