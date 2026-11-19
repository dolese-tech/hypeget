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


# ---------------------------------------------------------------- JavaScript runtime
# Since late 2025 YouTube only hands out its HD/4K formats to clients that can run its
# player JavaScript. yt-dlp does that through an external runtime (Deno preferred) plus
# the yt-dlp-ejs package. Without one, YouTube offers only a low-quality fallback.
_RUNTIMES = ("deno", "node", "bun")


def js_runtime() -> tuple[str, str] | None:
    """(name, path) of the JavaScript runtime yt-dlp should use, if any."""
    import shutil
    import sys
    if getattr(sys, "frozen", False):                 # bundled next to HyperGet.exe
        here = os.path.dirname(sys.executable)
        for name in _RUNTIMES:
            for p in (os.path.join(here, name + ".exe"), os.path.join(here, name)):
                if os.path.isfile(p):
                    return name, p
    for name in _RUNTIMES:
        p = shutil.which(name)
        if p:
            return name, p
    return None


def _ejs_installed() -> bool:
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def youtube_hd_ready() -> bool:
    """True when YouTube's HD/4K formats can be unlocked."""
    return js_runtime() is not None and _ejs_installed()


def _cookie_file(url: str, cookie_header: str) -> str | None:
    """Turn a Cookie header forwarded by the browser extension into a Netscape cookie
    file yt-dlp can use (helps with YouTube's 'confirm you're not a bot' checks)."""
    import tempfile
    import urllib.parse
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host or not cookie_header:
        return None
    parts = host.split(".")
    domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else host
    if host.endswith("youtu.be"):
        domain = ".youtube.com"
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookie_header.split(";"):
        name, sep, value = pair.strip().partition("=")
        if sep and name and "\t" not in name + value and "\n" not in name + value:
            lines.append("\t".join([domain, "TRUE", "/", "TRUE", "0", name, value]))
    if len(lines) == 1:
        return None
    fd, path = tempfile.mkstemp(prefix="hyperget-cookies-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _base_opts(headers: dict | None, url: str = "") -> dict:
    h = net.clean_headers(headers)
    cookie = h.pop("Cookie", None)
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True}
    if h:
        opts["http_headers"] = h
    rt = js_runtime()
    if rt:
        opts["js_runtimes"] = {rt[0]: {"path": rt[1]}}
    if cookie and url:
        cf = _cookie_file(url, cookie)
        if cf:
            opts["cookiefile"] = cf
    return opts


def _cleanup(opts: dict) -> None:
    cf = opts.get("cookiefile")
    if cf:
        try:
            os.remove(cf)
        except OSError:
            pass


# ---------------------------------------------------------------- quality list (like IDM)
_NAMES = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}
_CODECS = {"avc1": "H.264", "avc3": "H.264", "vp09": "VP9", "vp9": "VP9", "av01": "AV1", "hev1": "H.265", "hvc1": "H.265"}


def _codec(f: dict) -> str:
    c = (f.get("vcodec") or "").split(".")[0].lower()
    return _CODECS.get(c, c.upper())


def _is_h264(f: dict) -> bool:
    return (f.get("vcodec") or "").lower().startswith(("avc1", "avc3"))


def _label(h: int, fps: float) -> str:
    name = _NAMES.get(h, "")
    return f"{h}p" + (f"{round(fps)}" if fps and fps > 31 else "") + (f" {name}" if name else "")


def build_options(info: dict, can_merge: bool) -> list[dict]:
    """One choice per resolution, best version of each, like IDM's menu:
    H.264 in MP4 where YouTube has it (plays everywhere), otherwise VP9/AV1 in MKV."""
    formats = info.get("formats") or []
    duration = info.get("duration") or 0
    audio = [f for f in formats if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")]
    best_audio = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    m4a = [f for f in audio if f.get("ext") == "m4a"]
    best_m4a = max(m4a, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)

    video = [f for f in formats if f.get("height") and f.get("vcodec") not in (None, "none")]
    if not can_merge:
        video = [f for f in video if f.get("acodec") not in (None, "none")]   # needs audio already in
    by_height: dict[int, list[dict]] = {}
    for f in video:
        by_height.setdefault(int(f["height"]), []).append(f)

    options = []
    for h in sorted(by_height, reverse=True):
        group = by_height[h]
        fps = max((f.get("fps") or 0) for f in group)
        rate = lambda f: (f.get("fps") or 0, f.get("tbr") or 0)  # noqa: E731
        h264 = [f for f in group if _is_h264(f)]
        if h264:
            pick, container = max(h264, key=rate), "mp4"
            fmt = (f"bv*[height={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height={h}][vcodec^=avc]+ba"
                   f"/bv*[height<={h}]+ba/b[height<={h}]") if can_merge else f"b[height<={h}]"
            audio_f = best_m4a or best_audio
        else:
            pick, container = max(group, key=rate), "mkv"
            fmt = f"bv*[height={h}]+ba/bv*[height<={h}]+ba/b[height<={h}]" if can_merge else f"b[height<={h}]"
            audio_f = best_audio
        muxed = pick.get("acodec") not in (None, "none")
        size = _fsize(pick, duration) + (0 if muxed else _fsize(audio_f, duration))
        label = _label(h, fps)
        options.append({
            "id": f"v{h}", "label": label, "quality": f"{h}p", "height": h,
            "format": fmt, "container": container,
            "est_size": size or None, "detail": f"{container.upper()} · {_codec(pick)}",
        })
    if best_audio:
        a = best_m4a or best_audio
        options.append({"id": "audio", "label": "Audio only", "quality": "audio", "height": 0,
                        "format": "ba[ext=m4a]/ba/b", "container": (a.get("ext") or "m4a"),
                        "est_size": _fsize(a, duration) or None,
                        "detail": f"{(a.get('ext') or 'm4a').upper()} · {round(a.get('abr') or a.get('tbr') or 0)} kbps"})
    if not options:
        options.append({"id": "best", "label": "Best", "quality": "", "format": "b", "container": "mp4",
                        "est_size": None, "detail": ""})
    return options


def inspect(url: str, headers: dict | None = None) -> dict:
    if yt_dlp is None:
        raise DownloadError("Site support not installed (pip install yt-dlp)")
    opts = _base_opts(headers, url)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        raise DownloadError(msg[:200]) from e
    finally:
        _cleanup(opts)
    if info.get("_type") == "playlist":
        raise DownloadError("Playlists are not supported yet; open a single video")
    options = build_options(info, ffmpeg_path() is not None)
    out = {"kind": "site", "title": info.get("title") or "video", "duration": info.get("duration") or 0,
           "thumbnail": info.get("thumbnail"), "options": options}
    if "youtube" in (info.get("extractor_key") or "").lower() and not youtube_hd_ready():
        out["note"] = "HD and 4K need HyperGet's YouTube components; reinstall HyperGet to get them."
    return out


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
    container = str(dl.options.get("container") or ("m4a" if audio_only else "mp4")).lower()
    if container not in ("mp4", "mkv", "webm", "m4a", "opus", "mp3"):
        container = "m4a" if audio_only else "mp4"
    if not dl.probed:
        ctx.place(dl, "audio." + container if audio_only else "video." + container)
    os.makedirs(dl.save_dir, exist_ok=True)
    if not dl.probed and not dl.filename_locked:
        ext = "." + container
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

    opts = _base_opts(dl.headers, dl.url)
    opts.update({
        "format": dl.options.get("format") or "b",
        "outtmpl": stem + ".%(ext)s",
        "progress_hooks": [hook],
        "continuedl": True,
        "ratelimit": ctx.throttle.limit or None,
        "concurrent_fragment_downloads": max(1, min(dl.max_connections, 8)),
    })
    if not audio_only and ffmpeg_path():
        opts["merge_output_format"] = container if container in ("mp4", "mkv", "webm") else "mp4"
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
    finally:
        _cleanup(opts)
    if final and os.path.exists(final):
        dl.filename = os.path.basename(final)
        dl.size = dl.downloaded = os.path.getsize(final)
