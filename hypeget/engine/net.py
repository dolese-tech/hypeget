"""Small HTTP helpers on top of urllib (no third-party HTTP dependency)."""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 HyperGet/0.1"
)
TIMEOUT = 20
CHUNK = 64 * 1024

# Headers the browser extension may forward so authenticated/referer-checked
# downloads work. Anything else is dropped.
FORWARDABLE = {"cookie", "referer", "authorization", "user-agent", "origin", "accept-language"}


def clean_headers(headers: dict | None) -> dict:
    out = {}
    for k, v in (headers or {}).items():
        if k.lower() in FORWARDABLE and isinstance(v, str) and v and "\n" not in v and "\r" not in v:
            out[k.title()] = v
    return out


def open_url(url: str, headers: dict | None = None, range_: tuple[int, int | None] | None = None,
             method: str = "GET", timeout: float = TIMEOUT):
    h = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
    h.update(clean_headers(headers))
    if range_ is not None:
        start, end = range_
        h["Range"] = f"bytes={start}-{'' if end is None else end}"
    req = urllib.request.Request(url, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_bytes(url: str, headers: dict | None = None, limit: int = 50 * 1024 * 1024) -> bytes:
    with open_url(url, headers) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("response too large")
    return data


def fetch_text(url: str, headers: dict | None = None) -> tuple[str, str]:
    """Return (text, final_url)."""
    with open_url(url, headers) as r:
        final = r.geturl()
        data = r.read(10 * 1024 * 1024)
    return data.decode("utf-8", "replace"), final


_SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, default: str = "download") -> str:
    name = urllib.parse.unquote(name or "").strip().strip(".")
    name = _SAFE.sub("_", name)[:200]
    return name or default


def filename_from_url(url: str, default: str = "download") -> str:
    path = urllib.parse.urlparse(url).path
    return safe_filename(path.rsplit("/", 1)[-1], default)


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or ""


def _disposition_name(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", value, re.I)
    if m:
        return safe_filename(m.group(1).strip('"'))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', value, re.I)
    if m:
        return safe_filename(m.group(1))
    return None


HLS_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "audio/x-mpegurl"}


@dataclass
class ProbeResult:
    url: str              # final URL after redirects
    filename: str
    size: int | None
    resumable: bool
    content_type: str
    is_hls: bool


def probe(url: str, headers: dict | None = None) -> ProbeResult:
    """Ask for byte 0 only: tells us size, range support and the real filename."""
    try:
        resp = open_url(url, headers, range_=(0, 0))
    except urllib.error.HTTPError as e:
        if e.code == 416:  # empty file or ranges refused outright
            resp = open_url(url, headers)
        else:
            raise
    with resp:
        final = resp.geturl()
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        name = _disposition_name(resp.headers.get("Content-Disposition")) or filename_from_url(final)
        size = None
        resumable = False
        if resp.status == 206:
            m = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range", ""))
            if m:
                size = int(m.group(1))
                resumable = True
        else:
            cl = resp.headers.get("Content-Length")
            size = int(cl) if cl and cl.isdigit() else None
    is_hls = ctype in HLS_TYPES or urllib.parse.urlparse(final).path.lower().endswith(".m3u8")
    return ProbeResult(final, name, size, resumable, ctype, is_hls)
