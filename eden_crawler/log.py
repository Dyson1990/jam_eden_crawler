import hashlib
import logging
import os
import shutil


def _log_root():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def _spider_dir(spider_name):
    return os.path.join(_log_root(), spider_name)


def setup_logging(spider):
    """Suppress scrapy noise, redirect logs to logs/<spider>/."""
    log_dir = _spider_dir(spider.name)
    if os.path.exists(log_dir):
        shutil.rmtree(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    for name in (
        "scrapy", "twisted", "filelock", "h2", "httpcore",
        "httpx", "urllib3", "asyncio", "playwright",
        "scrapy.utils.log", "scrapy.extensions",
        "scrapy.crawler", "scrapy.statscollectors",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("scrapy.core.engine").setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(os.path.join(log_dir, "spider.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(fh)

    return log_dir


def save_body(spider_name, url, body):
    """Save response body to logs/<spider>/<hash>.html."""
    d = _spider_dir(spider_name)
    os.makedirs(d, exist_ok=True)
    fname = hashlib.md5(url.encode()).hexdigest()[:8] + ".html"
    fpath = os.path.join(d, fname)
    with open(fpath, "wb") as f:
        f.write(body)
    return fpath
