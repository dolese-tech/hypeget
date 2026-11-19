"""Optional site extractor (YouTube and other video sites) backed by yt-dlp.

yt-dlp is an optional dependency: ``pip install hypeget[sites]``. When it is
not installed, site pages simply aren't offered in the quality picker.

Note: many sites' terms of service restrict downloading. Only download
content you have the right to save (your own uploads, Creative Commons,
content the site offers for download, etc.).
"""
from __future__ import annotations

import os
import re

from . import net
from .download import CONNECTING, DOWNLOADING, MERGING, Download, unique_path
from .hls import ffmpeg_path
from .segments import DownloadError, RunContext, Stopped

try:  # pragma: no cover - depends on optional install
    import yt_dlp  # type: ignore
except Exception:  # noqa: BLE001
    yt_dlp = None


def available() -> bool:
    return yt_dlp is not None


_extractors = None


def supports(url: str) -> bool:
    """True if a dedicated (non-generic) yt-dlp extractor handles this URL."""
    global _extractors
    if yt_dlp is None:
        return False
    if _extractors is None:
        _extractors = [e for e in yt_dlp.extractor.gen_extractor_classes() if e.IE_NAME != "generic"]
    return any(e.suitable(url) for e in _extractors)


def _base_opts(headers: dict | None) -> dict:
    h = net.clean_headers(headers)
    h.pop("Cookie", None)  # cookies are handled by yt-dlp's own cookie jar
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True}
    if h:
        opts["http_headers"] = h
    return opts


def inspect(url: str, headers: dict | None = None) -> dict:
    if yt_dlp is None:
        raise DownloadError("Site support not installed (pip install yt-dlp)")
    try:
        with yt_dlp.YoutubeDL(_base_opts(headers)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        raise DownloadError(msg[:200]) from e
    if info.get("_type") == "playlist":
        raise DownloadError("Playlists are not supported yet; open a single video")
    formats = info.get("formats") or []
    duration = info.get("duration") or 0
    best_audio = max((f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")),
                     key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    audio_size = _fsize(best_audio, duration) if best_audio else 0
    can_merge = ffmpeg_path() is not None

    by_height: dict[int, dict] = {}
    for f in formats:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        muxed = f.get("acodec") not in (None, "none")
        if not muxed and not can_merge:
            continue
        size = _fsize(f, duration) + (0 if muxed else audio_size)
        cur = by_height.get(h)
        score = (f.get("tbr") or 0, f.get("ext") == "mp4")
        if cur is None or score > cur["_score"]:
            by_height[h] = {"_score": score, "size": size, "fps": f.get("fps") or 0,
                            "vcodec": (f.get("vcodec") or "").split(".")[0]}
    options = []
    for h in sorted(by_height, reverse=True):
        o = by_height[h]
        label = f"{h}p" + (f"{round(o['fps'])}" if o["fps"] and o["fps"] > 31 else "")
        options.append({
            "id": f"v{h}", "label": label, "quality": label, "height": h,
            "format": f"bv*[height<={h}]+ba/b[height<={h}]" if can_merge else f"b[height<={h}]",
            "est_size": o["size"] or None, "detail": f"MP4 · {o['vcodec'].upper()}" if o["vcodec"] else "MP4",
        })
    if best_audio:
        options.append({"id": "audio", "label": "Audio only", "quality": "audio", "height": 0,
                        "format": "ba/b", "est_size": audio_size or None,
                        "detail": f"{(best_audio.get('ext') or 'm4a').upper()} · {round(best_audio.get('abr') or 0)} kbps"})
    if not options:
        options.append({"id": "best", "label": "Best", "quality": "", "format": "b", "est_size": None, "detail": ""})
    return {"kind": "site", "title": info.get("title") or "video", "duration": duration,
            "thumbnail": info.get("thumbnail"), "options": options}


def _fsize(f: dict | None, duration: float) -> int:
    if not f:
        return 0
    if f.get("filesize"):
        return int(f["filesize"])
    if f.get("filesize_approx"):
        return int(f["filesize_approx"])
    if f.get("tbr") and duration:
        return int(f["tbr"] * 1000 / 8 * duration)
    return 0


def run_site(dl: Download, ctx: RunContext) -> None:
    if yt_dlp is None:
        raise DownloadError("Site support not installed (pip install yt-dlp)")
    dl.status = CONNECTING
    ctx.on_change()
    audio_only = dl.quality == "audio"
    if not dl.probed:
        ctx.place(dl, "audio.m4a" if audio_only else "video.mp4")
    os.makedirs(dl.save_dir, exist_ok=True)
    if not dl.probed and not dl.filename_locked:
        ext = ".m4a" if audio_only else ".mp4"
        stem = net.safe_filename(dl.title or "video")
        if dl.quality and not audio_only:
            stem += f"_{dl.quality}"
        dl.filename = unique_path(dl.save_dir, stem + ext)
    dl.probed = True
    dl.resumable = True
    stem = os.path.splitext(dl.target_path)[0]

    def hook(d):
        if ctx.stop.is_set():
            raise Stopped()
        if d.get("status") == "downloading":
            dl.status = DOWNLOADING
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                dl.size = int(total)
            dl.downloaded = int(d.get("downloaded_bytes") or 0)
            dl.connections = [dl.progress]
        elif d.get("status") == "finished":
            dl.status = MERGING

    opts = _base_opts(dl.headers)
    opts.update({
        "format": dl.options.get("format") or "b",
        "outtmpl": stem + ".%(ext)s",
        "progress_hooks": [hook],
        "continuedl": True,
        "ratelimit": ctx.throttle.limit or None,
        "concurrent_fragment_downloads": max(1, min(dl.max_connections, 8)),
    })
    if not audio_only and ffmpeg_path():
        opts["merge_output_format"] = "mp4"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(dl.url, download=True)
            final = info.get("requested_downloads", [{}])[0].get("filepath") or ydl.prepare_filename(info)
    except Stopped:
        raise
    except Exception as e:  # noqa: BLE001
        if ctx.stop.is_set():
            raise Stopped() from e
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        raise DownloadError(msg[:200]) from e
    if final and os.path.exists(final):
        dl.filename = os.path.basename(final)
        dl.size = dl.downloaded = os.path.getsize(final)
