import scrapy


class Asset:
    """Mark a URL for download. type: 'file' → local path, 'blob' → binary in DB."""
    def __init__(self, url, type="blob", referer=None):
        self.url = url
        self.type = type
        self.referer = referer

    def __repr__(self):
        return f"Asset(url={self.url!r}, type={self.type!r})"


class DynamicItem(scrapy.Item):
    """Auto-register fields on first assignment — no need to pre-define them."""

    def __setitem__(self, key, value):
        if key not in self.fields:
            self.fields[key] = scrapy.Field()
        super().__setitem__(key, value)
