"""Parse browser cookie strings into formats usable by scrapy/requests.

Usage:
    from tools.cookie_parser import parse, from_chrome_header

    cookies = parse("a=1; b=2")           # → {"a": "1", "b": "2"}
    info = from_chrome_header(raw_header)  # → {"cookies": {...}, "headers": {...}}
"""


def parse(raw):
    """Parse raw cookie header string into a dict.

    >>> parse("session=abc123; token=xyz789")
    {'session': 'abc123', 'token': 'xyz789'}
    """
    result = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def to_header(raw):
    """Wrap raw cookie string as a requests header dict."""
    return {"Cookie": raw.strip()}


def from_chrome_header(raw):
    """Parse full request header block copied from Chrome DevTools.

    Input: multi-line header block from Network → Copy → Copy request headers
    Returns: {"cookies": {key: val, ...}, "headers": {Key: Val, ...}}
    """
    result = {"cookies": {}, "headers": {}}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k.lower() == "cookie":
            result["cookies"] = parse(v)
        else:
            result["headers"][k] = v
    return result
