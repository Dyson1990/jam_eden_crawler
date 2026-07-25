import scrapy


class Asset:
    """Mark a URL for download. typ: 'file' → local path, 'blob' → binary in DB."""
    def __init__(self, url, typ="blob", referer=None):
        self.url = url
        self.typ = typ
        self.referer = referer

    def __repr__(self):
        return f"Asset(url={self.url!r}, typ={self.typ!r})"


class DynamicItem(scrapy.Item):
    """Auto-register fields on first assignment — no need to pre-define them."""

    def __setitem__(self, key, value):
        if key not in self.fields:
            self.fields[key] = scrapy.Field()
        super().__setitem__(key, value)
