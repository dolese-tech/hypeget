"""Scan a web page for links to downloadable files."""
from __future__ import annotations

import html
import re
import urllib.parse

from . import net
from .categories import _EXT, badge

_LINK = re.compile(r"""(?:href|src|data-src|content)\s*=\s*["']([^"'#]+)["']""", re.I)
_BARE = re.compile(r"""https?://[^\s"'<>()]+""", re.I)
_EXTS = set().union(*_EXT.values()) - {"ts", "sh", "txt"}


def grab(page_url: str, headers: dict | None = None, limit: int = 500) -> list[dict]:
    text, final = net.fetch_text(page_url, headers)
    seen, out = set(), []
    candidates = [m.group(1) for m in _LINK.finditer(text)] + _BARE.findall(text)
    for raw in candidates:
        url = urllib.parse.urljoin(final, html.unescape(raw.strip()))
        if not url.lower().startswith(("http://", "https://")) or url in seen:
            continue
        name = net.filename_from_url(url, "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _EXTS:
            continue
        seen.add(url)
        kind = "hls" if ext == "m3u8" else "http"
        out.append({"url": url, "filename": name, "badge": badge(name, kind), "kind": kind})
        if len(out) >= limit:
            break
    return out
