"""HLS (.m3u8) support: playlist parsing, quality variants, segment download.

Supports VOD playlists, master playlists with quality variants, separate
audio renditions, fMP4 (EXT-X-MAP), byte-range segments and standard
AES-128 encryption (key published in the playlist). Streams protected by DRM
(SAMPLE-AES, FairPlay, Widevine, PlayReady) are refused.
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass, field

from . import net
from .download import CONNECTING, DOWNLOADING, MERGING, Download, unique_path
from .segments import RETRIES, DownloadError, RunContext, Stopped, _http_error_text

_ATTR = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')


def _attrs(s: str) -> dict:
    return {k: v.strip('"') for k, v in _ATTR.findall(s)}


@dataclass
class Variant:
    uri: str
    bandwidth: int = 0
    width: int = 0
    height: int = 0
    codecs: str = ""
    audio_group: str = ""
    frame_rate: float = 0.0

    @property
    def label(self) -> str:
        if self.height:
            fps = f"{round(self.frame_rate)}" if self.frame_rate > 31 else ""
            return f"{self.height}p{fps}"
        if self.bandwidth:
            return f"{round(self.bandwidth / 1000)} kbps"
        return "Default"


@dataclass
class Rendition:
    uri: str
    group: str
    name: str = ""
    language: str = ""
    default: bool = False


@dataclass
class Key:
    method: str = "NONE"
    uri: str = ""
    iv: bytes | None = None
    keyformat: str = "identity"


@dataclass
class Segment:
    uri: str
    duration: float
    seq: int
    key: Key | None = None
    byterange: tuple[int, int] | None = None   # (start, end) inclusive


@dataclass
class MediaPlaylist:
    segments: list = field(default_factory=list)
    init: Segment | None = None
    endlist: bool = False

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)


@dataclass
class MasterPlaylist:
    variants: list = field(default_factory=list)
    audio: list = field(default_factory=list)


def is_master(text: str) -> bool:
    return "#EXT-X-STREAM-INF" in text


def parse_master(text: str, base: str) -> MasterPlaylist:
    m = MasterPlaylist()
    pending = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            a = _attrs(line.split(":", 1)[1])
            w = h = 0
            if "RESOLUTION" in a and "x" in a["RESOLUTION"]:
                w, h = (int(x) for x in a["RESOLUTION"].lower().split("x")[:2])
            pending = Variant("", int(a.get("BANDWIDTH", 0) or 0), w, h, a.get("CODECS", ""),
                              a.get("AUDIO", ""), float(a.get("FRAME-RATE", 0) or 0))
        elif line.startswith("#EXT-X-MEDIA:"):
            a = _attrs(line.split(":", 1)[1])
            if a.get("TYPE") == "AUDIO" and a.get("URI"):
                m.audio.append(Rendition(urllib.parse.urljoin(base, a["URI"]), a.get("GROUP-ID", ""),
                                         a.get("NAME", ""), a.get("LANGUAGE", ""),
                                         a.get("DEFAULT", "").upper() == "YES"))
        elif line and not line.startswith("#") and pending is not None:
            pending.uri = urllib.parse.urljoin(base, line)
            m.variants.append(pending)
            pending = None
    m.variants.sort(key=lambda v: (v.height, v.bandwidth), reverse=True)
    return m


def parse_media(text: str, base: str) -> MediaPlaylist:
    pl = MediaPlaylist()
    seq = 0
    duration = 0.0
    key: Key | None = None
    byterange = None
    next_offset = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            seq = int(line.split(":", 1)[1] or 0)
        elif line.startswith("#EXTINF:"):
            duration = float(line.split(":", 1)[1].split(",")[0] or 0)
        elif line.startswith("#EXT-X-KEY:"):
            a = _attrs(line.split(":", 1)[1])
            iv = a.get("IV")
            key = Key(a.get("METHOD", "NONE").upper(),
                      urllib.parse.urljoin(base, a["URI"]) if a.get("URI") else "",
                      bytes.fromhex(iv[2:] if iv.lower().startswith("0x") else iv) if iv else None,
                      a.get("KEYFORMAT", "identity"))
            if key.method == "NONE":
                key = None
        elif line.startswith("#EXT-X-MAP:"):
            a = _attrs(line.split(":", 1)[1])
            br = None
            if "BYTERANGE" in a:
                ln, _, off = a["BYTERANGE"].partition("@")
                o = int(off or 0)
                br = (o, o + int(ln) - 1)
            pl.init = Segment(urllib.parse.urljoin(base, a["URI"]), 0, -1, key, br)
        elif line.startswith("#EXT-X-BYTERANGE:"):
            ln, _, off = line.split(":", 1)[1].partition("@")
            o = int(off) if off else next_offset
            byterange = (o, o + int(ln) - 1)
            next_offset = byterange[1] + 1
        elif line.startswith("#EXT-X-ENDLIST"):
            pl.endlist = True
        elif line and not line.startswith("#"):
            pl.segments.append(Segment(urllib.parse.urljoin(base, line), duration, seq, key, byterange))
            seq += 1
            duration = 0.0
            byterange = None
    return pl


def check_supported(pl: MediaPlaylist) -> None:
    keys = [s.key for s in pl.segments if s.key] + ([pl.init.key] if pl.init and pl.init.key else [])
    for k in keys:
        if k.method != "AES-128" or k.keyformat.lower() != "identity":
            raise DownloadError("DRM-protected stream (not supported)")
    if not pl.endlist:
        raise DownloadError("Live streams are not supported yet")
    if not pl.segments:
        raise DownloadError("Empty playlist")


def ffmpeg_path() -> str | None:
    """FFmpeg bundled next to HyperGet.exe (packaged build) wins over PATH."""
    import sys
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        for name in ("ffmpeg.exe", "ffmpeg"):
            for p in (os.path.join(here, name), os.path.join(here, "ffmpeg", name)):
                if os.path.isfile(p):
                    return p
    return shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Inspection (used by the quality picker)
# ---------------------------------------------------------------------------
def inspect(url: str, headers: dict | None = None) -> dict:
    text, final = net.fetch_text(url, headers)
    if not text.lstrip().startswith("#EXTM3U"):
        raise DownloadError("Not an HLS playlist")
    title = os.path.splitext(net.filename_from_url(final, "video"))[0]
    if not is_master(text):
        pl = parse_media(text, final)
        check_supported(pl)
        return {"kind": "hls", "title": title, "duration": pl.duration, "options": [
            {"id": "default", "label": "Default", "quality": "", "variant_url": final,
             "audio_url": "", "est_size": None, "detail": f"{len(pl.segments)} segments"}]}
    master = parse_master(text, final)
    if not master.variants:
        raise DownloadError("No playable variants")
    first, _ = net.fetch_text(master.variants[0].uri, headers)
    pl = parse_media(first, master.variants[0].uri)
    check_supported(pl)
    dur = pl.duration
    options, seen = [], set()
    for v in master.variants:
        if v.label in seen:
            continue
        seen.add(v.label)
        audio = _pick_audio(master, v)
        detail = []
        if v.width:
            detail.append(f"{v.width}×{v.height}")
        if v.codecs:
            detail.append(v.codecs.split(",")[0].split(".")[0].upper())
        options.append({
            "id": v.label, "label": v.label, "quality": v.label, "height": v.height,
            "bandwidth": v.bandwidth, "variant_url": v.uri, "audio_url": audio.uri if audio else "",
            "est_size": int(v.bandwidth * dur / 8) if v.bandwidth and dur else None,
            "detail": " · ".join(detail),
        })
    return {"kind": "hls", "title": title, "duration": dur, "options": options}


def _pick_audio(master: MasterPlaylist, v: Variant) -> Rendition | None:
    group = [r for r in master.audio if r.group == v.audio_group] if v.audio_group else []
    if not group:
        return None
    return next((r for r in group if r.default), group[0])


def _choose_variant(master: MasterPlaylist, quality: str) -> Variant:
    if quality:
        for v in master.variants:
            if v.label == quality:
                return v
        m = re.match(r"(\d+)p", quality)
        if m:
            want = int(m.group(1))
            below = [v for v in master.variants if v.height and v.height <= want]
            if below:
                return below[0]
    return master.variants[0]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
class _KeyCache:
    def __init__(self, headers):
        self.headers = headers
        self.keys: dict[str, bytes] = {}
        self.lock = threading.Lock()

    def get(self, uri: str) -> bytes:
        with self.lock:
            if uri not in self.keys:
                self.keys[uri] = net.fetch_bytes(uri, self.headers, limit=1024)
            return self.keys[uri]


def _decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    out = dec.update(data) + dec.finalize()
    try:
        unpad = padding.PKCS7(128).unpadder()
        return unpad.update(out) + unpad.finalize()
    except ValueError:
        return out


def _prepare(dl: Download, ctx: RunContext) -> tuple[MediaPlaylist, MediaPlaylist | None]:
    dl.status = CONNECTING
    ctx.on_change()
    try:
        variant_url = dl.options.get("variant_url") or ""
        audio_url = dl.options.get("audio_url") or ""
        if not variant_url:
            text, final = net.fetch_text(dl.url, dl.headers)
            if is_master(text):
                master = parse_master(text, final)
                if not master.variants:
                    raise DownloadError("No playable variants")
                v = _choose_variant(master, dl.quality)
                variant_url = v.uri
                a = _pick_audio(master, v)
                audio_url = a.uri if a else ""
                dl.quality = dl.quality or v.label
            else:
                variant_url = final
            dl.options["variant_url"] = variant_url
            dl.options["audio_url"] = audio_url
        vtext, vfinal = net.fetch_text(variant_url, dl.headers)
        video = parse_media(vtext, vfinal)
        check_supported(video)
        audio = None
        if audio_url:
            atext, afinal = net.fetch_text(audio_url, dl.headers)
            audio = parse_media(atext, afinal)
            check_supported(audio)
    except (DownloadError, Stopped):
        raise
    except Exception as e:  # noqa: BLE001
        raise DownloadError(_http_error_text(e)) from e

    if not dl.probed:
        ctx.place(dl, "video.ts")
        fmp4 = video.init is not None
        ext = ".mp4" if (ffmpeg_path() or fmp4) else ".ts"
        if not dl.filename_locked:
            stem = net.safe_filename(dl.title) if dl.title else \
                os.path.splitext(net.filename_from_url(dl.url, "video"))[0]
            if dl.quality and dl.quality not in stem:
                stem = f"{stem}_{dl.quality}"
            dl.filename = unique_path(dl.save_dir, stem + ext)
        dl.resumable = True
        dl.probed = True
    dl.parts_total = len(video.segments) + (len(audio.segments) if audio else 0)
    return video, audio


def run_hls(dl: Download, ctx: RunContext) -> None:
    video, audio = _prepare(dl, ctx)
    os.makedirs(dl.save_dir, exist_ok=True)
    ctx.check()
    work = dl.target_path + ".parts"
    os.makedirs(work, exist_ok=True)

    jobs: list[tuple[str, Segment]] = []
    if video.init:
        jobs.append(("v_init", video.init))
    jobs += [(f"v{i:06d}", s) for i, s in enumerate(video.segments)]
    if audio:
        if audio.init:
            jobs.append(("a_init", audio.init))
        jobs += [(f"a{i:06d}", s) for i, s in enumerate(audio.segments)]

    keys = _KeyCache(dl.headers)
    q: queue.Queue = queue.Queue()
    done = 0
    downloaded = 0
    for name, seg in jobs:
        path = os.path.join(work, name)
        if os.path.exists(path):
            if not name.endswith("_init"):
                done += 1
            downloaded += os.path.getsize(path)
        else:
            q.put((name, seg))
    dl.parts_done, dl.downloaded = done, downloaded
    dl.status = DOWNLOADING
    ctx.on_change()

    lock = threading.Lock()
    errors: list[str] = []
    live: dict[int, float] = {}

    def worker(wid: int):
        while not ctx.stop.is_set() and not errors:
            try:
                name, seg = q.get_nowait()
            except queue.Empty:
                return
            try:
                data = _fetch_segment(seg, dl, ctx, keys, wid, live)
            except Stopped:
                return
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(_http_error_text(e))
                return
            path = os.path.join(work, name)
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
            with lock:
                if not name.endswith("_init"):
                    dl.parts_done += 1
            live.pop(wid, None)

    n = max(1, min(dl.max_connections, q.qsize() or 1))
    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        dl.connections = [round(v, 3) for v in live.values()]
        time.sleep(0.2)
    dl.connections = []
    if errors:
        raise DownloadError(errors[0])
    ctx.check()

    dl.status = MERGING
    ctx.on_change()
    _merge(dl, work, video, audio)
    shutil.rmtree(work, ignore_errors=True)


def _fetch_segment(seg: Segment, dl: Download, ctx: RunContext, keys: _KeyCache,
                   wid: int, live: dict) -> bytes:
    last = None
    for attempt in range(RETRIES):
        ctx.check()
        buf = bytearray()
        try:
            with net.open_url(seg.uri, dl.headers, range_=seg.byterange) as r:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    ctx.check()
                    chunk = r.read(net.CHUNK)
                    if not chunk:
                        break
                    ctx.throttle.consume(len(chunk), ctx.stop)
                    buf += chunk
                    dl.downloaded += len(chunk)
                    live[wid] = len(buf) / total if total else 0.5
            data = bytes(buf)
            if seg.key and seg.key.method == "AES-128":
                iv = seg.key.iv or max(seg.seq, 0).to_bytes(16, "big")
                data = _decrypt(data, keys.get(seg.key.uri), iv)
            return data
        except Stopped:
            dl.downloaded -= len(buf)
            raise
        except Exception as e:  # noqa: BLE001
            dl.downloaded -= len(buf)
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404, 410):
                break
            if ctx.stop.wait(min(2 ** attempt, 10)):
                raise Stopped()
    raise DownloadError(_http_error_text(last) if last else "Segment failed")


def _concat(work: str, prefix: str, count: int, has_init: bool, out_path: str) -> None:
    with open(out_path, "wb") as out:
        names = ([f"{prefix}_init"] if has_init else []) + [f"{prefix}{i:06d}" for i in range(count)]
        for name in names:
            with open(os.path.join(work, name), "rb") as f:
                shutil.copyfileobj(f, out, 1024 * 1024)


def _merge(dl: Download, work: str, video: MediaPlaylist, audio: MediaPlaylist | None) -> None:
    fmp4 = video.init is not None
    vraw = os.path.join(work, "video" + (".mp4" if fmp4 else ".ts"))
    _concat(work, "v", len(video.segments), fmp4, vraw)
    araw = None
    if audio:
        araw = os.path.join(work, "audio" + (".mp4" if audio.init else ".ts"))
        _concat(work, "a", len(audio.segments), audio.init is not None, araw)

    target = dl.target_path
    ff = ffmpeg_path()
    if ff and target.endswith(".mp4"):
        cmd = [ff, "-y", "-loglevel", "error", "-i", vraw]
        if araw:
            cmd += ["-i", araw, "-map", "0:v:0?", "-map", "1:a:0?", "-map", "0:a:0?"]
        cmd += ["-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", target + ".tmp.mp4"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            os.replace(target + ".tmp.mp4", target)
            dl.size = os.path.getsize(target)
            return
        # fall back to raw stream if remux fails
        try:
            os.remove(target + ".tmp.mp4")
        except OSError:
            pass
        if not fmp4:
            target = os.path.splitext(target)[0] + ".ts"
            dl.filename = os.path.basename(target)
    os.replace(vraw, target)
    if araw:  # no ffmpeg to mux: keep audio next to the video
        stem, _ = os.path.splitext(target)
        os.replace(araw, stem + ".audio" + os.path.splitext(araw)[1])
    dl.size = os.path.getsize(target)
