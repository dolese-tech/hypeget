"""Work out what a link is and which qualities can be downloaded (quality picker)."""
from __future__ import annotations

from . import hls, net, sites
from .categories import badge
from .segments import DownloadError, _http_error_text


def inspect(url: str, headers: dict | None = None) -> dict:
    """Return {kind, title, options:[{id,label,quality,est_size,detail,...}], ...}."""
    if sites.supports(url):
        return sites.inspect(url, headers)
    try:
        p = net.probe(url, headers)
    except Exception as e:  # noqa: BLE001
        raise DownloadError(_http_error_text(e)) from e
    if p.is_hls:
        return hls.inspect(p.url, headers)
    return {
        "kind": "http", "title": p.filename, "filename": p.filename,
        "options": [{"id": "file", "label": badge(p.filename), "quality": "",
                     "est_size": p.size, "detail": "Resume supported" if p.resumable else "No resume"}],
    }
