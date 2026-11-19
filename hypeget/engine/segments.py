"""Multi-connection HTTP downloader with dynamic segment splitting.

The file is pre-allocated as ``name.part``. It is split into N byte ranges
(one per connection). When a connection finishes its range it steals half of
the largest remaining range, so all connections stay busy until the end,
which is what makes the per-connection bars in the details panel move
together.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error

from . import net
from .download import CONNECTING, DOWNLOADING, Download, unique_path

MIN_SPLIT = 512 * 1024      # don't split ranges smaller than this
RETRIES = 6


class DownloadError(Exception):
    pass


class Stopped(Exception):
    pass


class RunContext:
    """What a runner gets from the manager."""

    def __init__(self, throttle, stop: threading.Event, on_change=None, base_dir: str | None = None):
        self.throttle = throttle
        self.stop = stop
        self.on_change = on_change or (lambda: None)
        self.base_dir = base_dir

    def place(self, dl: Download, filename: str) -> None:
        """Put an auto-filed download in its category folder (Compressed, Video ...)."""
        if dl.options.get("auto_dir") and self.base_dir:
            from .categories import category_for
            dl.save_dir = os.path.join(self.base_dir, category_for(filename, dl.kind))
            os.makedirs(dl.save_dir, exist_ok=True)

    def check(self):
        if self.stop.is_set():
            raise Stopped()


def _http_error_text(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        r = e.reason
        return "Timeout" if "timed out" in str(r) else f"Network error: {r}"
    if isinstance(e, TimeoutError) or "timed out" in str(e):
        return "Timeout"
    return str(e) or e.__class__.__name__


def prepare_http(dl: Download, ctx: RunContext) -> net.ProbeResult | None:
    """Probe the URL once to learn size / resume support / real filename."""
    if dl.probed:
        return None
    dl.status = CONNECTING
    ctx.on_change()
    try:
        p = net.probe(dl.url, dl.headers)
    except Exception as e:  # noqa: BLE001
        raise DownloadError(_http_error_text(e)) from e
    with dl.lock:
        if p.is_hls:
            return p
        ctx.place(dl, dl.filename if dl.filename_locked else p.filename)
        if not dl.filename_locked:
            dl.filename = unique_path(dl.save_dir, p.filename)
        dl.size = p.size
        dl.resumable = p.resumable
        dl.probed = True
    return p


def run_http(dl: Download, ctx: RunContext) -> None:
    p = prepare_http(dl, ctx)
    if p is not None and p.is_hls:
        # Link turned out to be an HLS playlist: hand over to the HLS runner.
        from .hls import run_hls
        dl.kind = "hls"
        dl.url = p.url
        return run_hls(dl, ctx)
    os.makedirs(dl.save_dir, exist_ok=True)
    ctx.check()
    part = dl.target_path + ".part"

    if dl.resumable and dl.size:
        _run_segmented(dl, ctx, part)
    else:
        _run_single(dl, ctx, part)

    ctx.check()
    os.replace(part, dl.target_path)


# ---------------------------------------------------------------------------
def _run_single(dl: Download, ctx: RunContext, part: str) -> None:
    """Server doesn't support ranges (or size unknown): one stream from byte 0."""
    dl.status = DOWNLOADING
    dl.downloaded = 0
    dl.segments = []
    ctx.on_change()
    last_err = None
    for attempt in range(RETRIES):
        ctx.check()
        try:
            dl.downloaded = 0
            with net.open_url(dl.url, dl.headers) as r, open(part, "wb") as f:
                if dl.size is None:
                    cl = r.headers.get("Content-Length")
                    dl.size = int(cl) if cl and cl.isdigit() else None
                while True:
                    ctx.check()
                    chunk = r.read(net.CHUNK)
                    if not chunk:
                        break
                    ctx.throttle.consume(len(chunk), ctx.stop)
                    f.write(chunk)
                    dl.downloaded += len(chunk)
                    dl.connections = [dl.progress] if dl.size else []
            if dl.size is not None and dl.downloaded < dl.size:
                raise DownloadError("Connection closed early")
            dl.size = dl.downloaded
            dl.connections = []
            return
        except Stopped:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code not in (408, 429):
                break
            ctx.stop.wait(min(2 ** attempt, 10))
    raise DownloadError(_http_error_text(last_err))


# ---------------------------------------------------------------------------
class _Segmented:
    def __init__(self, dl: Download, ctx: RunContext, part: str):
        self.dl, self.ctx, self.part = dl, ctx, part
        self.lock = threading.Lock()
        self.active: dict[int, list] = {}     # worker id -> segment
        self.error: str | None = None
        self.fatal = threading.Event()

    def plan(self):
        dl = self.dl
        if dl.segments:
            return
        n = max(1, min(dl.max_connections, dl.size // MIN_SPLIT or 1))
        step = dl.size // n
        segs = []
        for i in range(n):
            start = i * step
            end = dl.size - 1 if i == n - 1 else (i + 1) * step - 1
            segs.append([start, end, start])
        dl.segments = segs

    def next_segment(self, wid: int):
        """Give a worker an unclaimed segment, or split the biggest one."""
        with self.lock:
            claimed = {id(s) for s in self.active.values()}
            for s in self.dl.segments:
                if s[2] <= s[1] and id(s) not in claimed:
                    self.active[wid] = s
                    return s
            # steal half of the largest remaining range
            best, best_rem = None, 0
            for s in self.active.values():
                rem = s[1] - s[2] + 1
                if rem > best_rem:
                    best, best_rem = s, rem
            if best is None or best_rem < 2 * MIN_SPLIT:
                self.active.pop(wid, None)
                return None
            mid = best[2] + best_rem // 2
            new = [mid, best[1], mid]
            best[1] = mid - 1
            self.dl.segments.append(new)
            self.active[wid] = new
            return new

    def worker(self, wid: int):
        try:
            with open(self.part, "r+b") as f:
                while not self.ctx.stop.is_set() and not self.fatal.is_set():
                    seg = self.next_segment(wid)
                    if seg is None:
                        return
                    self.fetch(seg, f)
        except Stopped:
            pass
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.error = self.error or _http_error_text(e)
            self.fatal.set()
        finally:
            with self.lock:
                self.active.pop(wid, None)

    def fetch(self, seg: list, f):
        attempt = 0
        while True:
            with self.lock:
                if seg[2] > seg[1]:
                    return
                start, end = seg[2], seg[1]
            try:
                with net.open_url(self.dl.url, self.dl.headers, range_=(start, end)) as r:
                    if r.status != 206:
                        raise DownloadError("Server stopped honouring byte ranges")
                    while True:
                        if self.ctx.stop.is_set() or self.fatal.is_set():
                            raise Stopped()
                        chunk = r.read(net.CHUNK)
                        if not chunk:
                            break
                        self.ctx.throttle.consume(len(chunk), self.ctx.stop)
                        with self.lock:
                            room = seg[1] - seg[2] + 1      # seg[1] may shrink after a split
                            if room <= 0:
                                return
                            chunk = chunk[:room]
                            pos = seg[2]
                            seg[2] += len(chunk)
                            self.dl.downloaded += len(chunk)
                        f.seek(pos)
                        f.write(chunk)
                        if len(chunk) == room:
                            return
                attempt = 0 if seg[2] > start else attempt + 1
                if seg[2] <= seg[1] and attempt >= RETRIES:
                    raise DownloadError("Connection closed early")
            except (Stopped, DownloadError):
                raise
            except Exception as e:  # noqa: BLE001
                if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code not in (408, 429):
                    raise
                attempt += 1
                if attempt >= RETRIES:
                    raise
                if self.ctx.stop.wait(min(2 ** attempt, 10)):
                    raise Stopped()

    def snapshot(self):
        with self.lock:
            out = []
            for s in self.active.values():
                total = s[1] - s[0] + 1
                out.append(round((s[2] - s[0]) / total, 3) if total > 0 else 1.0)
            return out


def _run_segmented(dl: Download, ctx: RunContext, part: str) -> None:
    mode = "r+b" if os.path.exists(part) else "wb"
    with open(part, mode) as f:
        f.truncate(dl.size)
    if mode == "wb":
        dl.segments = []
    job = _Segmented(dl, ctx, part)
    job.plan()
    dl.downloaded = sum(s[2] - s[0] for s in dl.segments)
    dl.status = DOWNLOADING
    ctx.on_change()

    threads = [threading.Thread(target=job.worker, args=(i,), daemon=True)
               for i in range(dl.max_connections)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        dl.connections = job.snapshot()
        time.sleep(0.2)
    dl.connections = []
    if job.error:
        raise DownloadError(job.error)
    ctx.check()
    if any(s[2] <= s[1] for s in dl.segments) or dl.downloaded < dl.size:
        raise DownloadError("Incomplete download")
