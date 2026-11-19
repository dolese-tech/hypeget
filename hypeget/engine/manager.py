"""Owns every download: queue, start/pause/resume/delete, speed, persistence."""
from __future__ import annotations

import os
import threading
import time
import urllib.parse

from ..config import Config
from ..storage.state import StateStore
from . import hls, net, sites
from .categories import CATEGORIES, category_for
from .download import (ACTIVE, COMPLETE, ERROR, PAUSED, QUEUED, UNFINISHED, Download)
from .scheduler import Scheduler
from .segments import DownloadError, RunContext, Stopped, run_http
from .throttle import Throttle

RUNNERS = {"http": run_http, "hls": hls.run_hls, "site": sites.run_site}


def guess_kind(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        return "hls"
    if sites.supports(url):
        return "site"
    return "http"


class Manager:
    def __init__(self, config: Config | None = None, autostart: bool = True):
        self.config = config or Config()
        self.store = StateStore(self.config.home)
        self.throttle = Throttle(self.config.settings.speed_limit)
        self.scheduler = Scheduler()
        self._lock = threading.RLock()
        self.downloads: dict[str, Download] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}
        self._deleted: set[str] = set()
        self._dirty = False
        self._last_save = 0.0
        self._running = True
        self.queue_running = True
        self.grabber_projects = 0
        self.ui_show = None          # set by the app window: ui_show(command) brings it forward
        for d in self.store.load():
            self.downloads[d.id] = d
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        if autostart:
            self._ticker.start()

    # ------------------------------------------------------------------ API
    def add(self, url: str, *, kind: str | None = None, filename: str | None = None,
            save_dir: str | None = None, quality: str = "", options: dict | None = None,
            headers: dict | None = None, title: str = "", page_url: str = "",
            start: bool = True, connections: int | None = None) -> Download:
        url = url.strip()
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError("Only http(s) links are supported")
        s = self.config.settings
        kind = kind or guess_kind(url)
        opts = dict(options or {})
        guess_name = filename or net.filename_from_url(url)
        if not save_dir:
            opts["auto_dir"] = s.file_by_category
            save_dir = os.path.join(s.download_dir, category_for(guess_name, kind)) \
                if s.file_by_category else s.download_dir
        dl = Download(url=url, save_dir=save_dir, kind=kind, title=title, page_url=page_url,
                      quality=quality, options=opts, headers=net.clean_headers(headers),
                      max_connections=connections or s.connections)
        if filename:
            dl.filename = net.safe_filename(filename)
            dl.filename_locked = True
        else:
            # Show a real name right away instead of "Connecting..."
            if kind == "http":
                dl.filename = guess_name
            elif title:
                dl.filename = net.safe_filename(title) + ".mp4"
            else:
                dl.filename = os.path.splitext(guess_name)[0] + ".mp4"
        dl.status = QUEUED if start else PAUSED
        dl.in_queue = start
        with self._lock:
            self.downloads[dl.id] = dl
            self._dirty = True
        self._schedule()
        return dl

    def get(self, did: str) -> Download | None:
        return self.downloads.get(did)

    def resume(self, did: str) -> None:
        dl = self.downloads.get(did)
        if not dl or dl.status in ACTIVE or dl.status == COMPLETE:
            return
        dl.error = ""
        dl.status = QUEUED
        dl.in_queue = True
        self._dirty = True
        self._schedule()

    def pause(self, did: str) -> None:
        dl = self.downloads.get(did)
        if not dl:
            return
        ev = self._stops.get(did)
        if ev:
            ev.set()
        elif dl.status == QUEUED:
            dl.status = PAUSED
        dl.in_queue = False
        self._dirty = True

    def stop_all(self) -> None:
        self.queue_running = False
        for did in list(self.downloads):
            self.pause(did)

    def start_queue(self) -> None:
        self.queue_running = True
        for dl in self.downloads.values():
            if dl.status in (PAUSED, ERROR) and dl.status != COMPLETE:
                self.resume(dl.id)
        self._schedule()

    def delete(self, did: str, remove_file: bool = False) -> None:
        dl = self.downloads.get(did)
        if not dl:
            return
        self._deleted.add(did)
        ev = self._stops.get(did)
        if ev:
            ev.set()
            t = self._threads.get(did)
            if t:
                t.join(timeout=5)
        with self._lock:
            self.downloads.pop(did, None)
            self._dirty = True
        self._cleanup_files(dl, remove_file)

    def redownload(self, did: str) -> None:
        dl = self.downloads.get(did)
        if not dl or dl.status in ACTIVE:
            return
        self._cleanup_files(dl, remove_file=False)
        dl.segments, dl.downloaded, dl.parts_done = [], 0, 0
        dl.probed, dl.error = False, ""
        dl.status = QUEUED
        self._schedule()

    def set_speed_limit(self, bps: int) -> None:
        self.config.update(speed_limit=bps)
        self.throttle.set_limit(self.config.settings.speed_limit)

    def update_settings(self, **changes) -> dict:
        self.config.update(**changes)
        self.throttle.set_limit(self.config.settings.speed_limit)
        self._schedule()
        return self.config.to_dict()

    def shutdown(self) -> None:
        self._running = False
        for ev in self._stops.values():
            ev.set()
        for t in list(self._threads.values()):
            t.join(timeout=5)
        self.save()

    def save(self) -> None:
        with self._lock:
            items = list(self.downloads.values())
        self.store.save(items)
        self._dirty = False
        self._last_save = time.monotonic()

    # ----------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        with self._lock:
            items = list(self.downloads.values())
        items.sort(key=lambda d: d.added, reverse=True)
        views = [d.to_view() for d in items]
        counts = {c: 0 for c in CATEGORIES}
        unfinished = finished = 0
        for d in items:
            if d.category in counts:
                counts[d.category] += 1
            if d.status == COMPLETE:
                finished += 1
            elif d.status in UNFINISHED:
                unfinished += 1
        active = [d for d in items if d.status in ACTIVE]
        waiting = [d for d in items if d.status == QUEUED]
        s = self.config.settings
        return {
            "downloads": views,
            "counts": {"all": len(items), "categories": counts, "unfinished": unfinished,
                       "finished": finished, "queues": 1 + (1 if s.scheduler_enabled else 0),
                       "grabber": self.grabber_projects},
            "active": len(active),
            "total_speed": sum(d.speed for d in active),
            "waiting": len(waiting),
            "queue_running": self.queue_running,
            "scheduler": self.scheduler.describe(s.scheduler_enabled, s.scheduler_start, s.scheduler_stop),
            "settings": self.config.to_dict(),
            "features": {"sites": sites.available(), "ffmpeg": hls.ffmpeg_path() is not None,
                         "youtube_hd": sites.available() and sites.youtube_hd_ready()},
        }

    # ------------------------------------------------------------ internals
    def _schedule(self) -> None:
        with self._lock:
            active = sum(1 for d in self.downloads.values() if d.id in self._threads)
            limit = self.config.settings.max_active
            queued = sorted((d for d in self.downloads.values()
                             if d.status == QUEUED and d.id not in self._threads), key=lambda d: d.added)
            for dl in queued:
                if active >= limit:
                    break
                self._launch(dl)
                active += 1

    def _launch(self, dl: Download) -> None:
        stop = threading.Event()
        self._stops[dl.id] = stop
        t = threading.Thread(target=self._run, args=(dl, stop), daemon=True, name=f"dl-{dl.id}")
        self._threads[dl.id] = t
        t.start()

    def _run(self, dl: Download, stop: threading.Event) -> None:
        ctx = RunContext(self.throttle, stop, self._mark_dirty, self.config.settings.download_dir)
        dl.reset_speed()
        try:
            RUNNERS[dl.kind](dl, ctx)
            dl.status = COMPLETE
            dl.finished_at = time.time()
            dl.segments = []
        except Stopped:
            dl.status = PAUSED
        except DownloadError as e:
            dl.status = PAUSED if stop.is_set() else ERROR
            dl.error = "" if stop.is_set() else str(e)
        except Exception as e:  # noqa: BLE001
            dl.status = ERROR
            dl.error = str(e) or e.__class__.__name__
        finally:
            dl.connections = []
            dl.reset_speed()
            with self._lock:
                self._threads.pop(dl.id, None)
                self._stops.pop(dl.id, None)
            self._dirty = True
            if dl.id not in self._deleted:
                self._schedule()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _cleanup_files(self, dl: Download, remove_file: bool) -> None:
        import shutil
        for p in (dl.target_path + ".part",):
            try:
                os.remove(p)
            except OSError:
                pass
        shutil.rmtree(dl.target_path + ".parts", ignore_errors=True)
        if remove_file and dl.status == COMPLETE:
            try:
                os.remove(dl.target_path)
            except OSError:
                pass

    def _tick_loop(self) -> None:
        while self._running:
            now = time.monotonic()
            for d in list(self.downloads.values()):
                d.update_speed(now)
            s = self.config.settings
            action = self.scheduler.check(s.scheduler_enabled, s.scheduler_start, s.scheduler_stop)
            if action == "start":
                self.start_queue()
            elif action == "stop":
                self.stop_all()
            if any(d.status in ACTIVE for d in self.downloads.values()):
                self._dirty = True
            if self._dirty and now - self._last_save > 2.0:
                try:
                    self.save()
                except OSError:
                    pass
            time.sleep(0.5)
