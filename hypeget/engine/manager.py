"""Owns every download: queue, start/pause/resume/delete, speed, persistence."""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
import urllib.parse

from ..config import Config
from ..storage.state import StateStore
from . import hls, net, sites
from .categories import CATEGORIES, category_for
from .download import (ACTIVE, COMPLETE, ERROR, PAUSED, QUEUED, UNFINISHED, Download)
from . import power
from .scheduler import Scheduler, in_window
from .stats import Stats
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


_NOT_RETRYABLE = ("HTTP 400", "HTTP 401", "HTTP 403", "HTTP 404", "HTTP 410", "DRM", "Live stream",
                  "Not an HLS", "Empty playlist", "Only http", "not supported", "Unsupported URL",
                  "Video unavailable", "Private video", "copyright")


def retryable(error: str) -> bool:
    """Worth trying again later: timeouts, dropped connections, busy servers.
    Not worth it: missing files, no permission, DRM and other permanent refusals."""
    return bool(error) and not any(x.lower() in error.lower() for x in _NOT_RETRYABLE)


class Manager:
    def __init__(self, config: Config | None = None, autostart: bool = True):
        self.config = config or Config()
        self.store = StateStore(self.config.home)
        self.throttle = Throttle(self.config.settings.speed_limit)
        self.scheduler = Scheduler()
        self._lock = threading.RLock()
        self.downloads: dict[str, Download] = {}
        self._seen_bytes: dict[str, int] = {}     # bytes counted so far per download (for statistics)
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}
        self._deleted: set[str] = set()
        self._dirty = False
        self._last_save = 0.0
        self._running = True
        self.queue_running = True
        self.grabber_projects = 0
        self.ui_show = None          # set by the app window: ui_show(command) brings it forward
        self.on_exit = None          # set by the app: quit HyperGet (for 'when done: exit')
        self.power = power.run       # replaced in tests
        self._had_work = False       # something ran since 'when done' was armed
        self.pending_action: dict | None = None   # {"action", "at"} countdown before when-done runs
        self._applied_limit = None
        self.stats = Stats(self.config.home)
        self._last_tick: float | None = None
        self._last_sample = 0.0
        self.cap_hit_month: str | None = None     # month the data cap was reached in
        for d in self.store.load():
            self.downloads[d.id] = d
            self._seen_bytes[d.id] = d.downloaded     # counted in an earlier session
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        if autostart:
            self._ticker.start()

    # ------------------------------------------------------------------ API
    def add(self, url: str, *, kind: str | None = None, filename: str | None = None,
            save_dir: str | None = None, quality: str = "", options: dict | None = None,
            headers: dict | None = None, title: str = "", page_url: str = "",
            start: bool = True, connections: int | None = None, group: str = "",
            thumbnail: str = "") -> Download:
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
                      max_connections=connections or s.connections, group=str(group or "")[:200],
                      thumbnail=thumbnail if str(thumbnail or "").startswith("https://") else "")
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
            self._seen_bytes[dl.id] = 0
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
        dl.retry_at = None
        dl.retries = 0
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
        dl.retry_at = None              # a paused download doesn't retry by itself
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
        self._apply_speed(force=True)

    def update_settings(self, **changes) -> dict:
        if "when_done" in changes:
            self.set_when_done(str(changes.pop("when_done")))
        self.config.update(**changes)
        self._apply_speed(force=True)
        self._schedule()
        return self.config.to_dict()

    # ---- speed rules -------------------------------------------------
    def active_rule(self, now=None) -> dict | None:
        """The first enabled speed rule whose days and hours include now."""
        now = now or dt.datetime.now()
        for r in self.config.settings.speed_rules:
            if not r.get("enabled"):
                continue
            start, end = r["start"], r["end"]
            # a window past midnight belongs to the day it started on
            day = now.weekday() if (start < end or now.strftime("%H:%M") >= start) else (now.weekday() - 1) % 7
            if day in r.get("days", []) and in_window(start, end, now):
                return r
        return None

    def effective_speed_limit(self, now=None) -> tuple[int, bool]:
        """(bytes/s, rule active?) - the matching rule's limit, else the normal limit."""
        r = self.active_rule(now)
        if r:
            return r["limit"], True
        return self.config.settings.speed_limit, False

    def _apply_speed(self, force: bool = False, now=None) -> None:
        limit, _ = self.effective_speed_limit(now)
        if force or limit != self._applied_limit:
            self.throttle.set_limit(limit)
            self._applied_limit = limit

    # ---- when all downloads finish ------------------------------------
    def set_when_done(self, action: str) -> None:
        if action not in ("nothing", "sleep", "shutdown", "exit"):
            action = "nothing"
        self.config.update(when_done=action)
        self.pending_action = None
        self._had_work = any(d.status in ACTIVE or d.status == QUEUED for d in self.downloads.values())

    def cancel_when_done(self) -> None:
        """Stop a running countdown and switch the action off."""
        self.pending_action = None
        self.config.update(when_done="nothing")

    def _busy(self) -> bool:
        return any(d.status in ACTIVE or d.status == QUEUED or d.retry_at for d in self.downloads.values())

    def _check_when_done(self, now: float) -> None:
        action = self.config.settings.when_done
        if action == "nothing":
            self.pending_action = None
            return
        if self._busy():
            self._had_work = True
            self.pending_action = None          # new work arrived: wait again
            return
        if not self._had_work:
            return
        if self.pending_action is None:
            self.pending_action = {"action": action, "at": now + 60}
            return
        if now >= self.pending_action["at"]:
            self.pending_action = None
            self._had_work = False
            self.config.update(when_done="nothing")     # once only: never a surprise later
            try:
                self.save()
            except OSError:
                pass
            if action == "exit":
                if self.on_exit:
                    self.on_exit()
            else:
                self.power(action)

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
        if self.stats.dirty:
            self.stats.save()
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
            "speed_rule_active": self.effective_speed_limit()[1],
            "speed_rule": (self.active_rule() or {}).get("name"),
            "data_cap": self.data_cap(),
            "cap_reached": self.cap_hit_month is not None,
            "today": self.stats.today(),
            "month_bytes": self.stats.month_bytes(),
            "plan": "preview",           # Pro features are free during the preview; licences come later
            "effective_speed_limit": self.effective_speed_limit()[0],
            "when_done": s.when_done,
            "pending_action": ({"action": self.pending_action["action"],
                                "in": max(0, round(self.pending_action["at"] - time.time()))}
                               if self.pending_action else None),
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
        self._had_work = True            # even a download finishing between two ticks counts
        stop = threading.Event()
        self._stops[dl.id] = stop
        t = threading.Thread(target=self._run, args=(dl, stop), daemon=True, name=f"dl-{dl.id}")
        self._threads[dl.id] = t
        t.start()

    def _run(self, dl: Download, stop: threading.Event) -> None:
        ctx = RunContext(self.throttle, stop, self._mark_dirty, self.config.settings.download_dir)
        dl.reset_speed()
        started = time.monotonic()
        try:
            RUNNERS[dl.kind](dl, ctx)
            dl.status = COMPLETE
            dl.finished_at = time.time()
            dl.segments = []
            dl.retries, dl.retry_at = 0, None
            self.stats.add_file()
        except Stopped:
            dl.status = PAUSED
        except DownloadError as e:
            dl.status = PAUSED if stop.is_set() else ERROR
            dl.error = "" if stop.is_set() else str(e)
            s = self.config.settings
            if dl.status == ERROR and retryable(dl.error) and dl.retries < s.auto_retry:
                dl.retry_at = time.time() + s.retry_delay * (2 ** dl.retries)
                dl.retries += 1
        except Exception as e:  # noqa: BLE001
            dl.status = ERROR
            dl.error = str(e) or e.__class__.__name__
        finally:
            dl.active_seconds += time.monotonic() - started
            if dl.status == ERROR and not dl.retry_at:
                self.stats.add_file(failed=True)
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

    def _count_traffic(self, now: float) -> None:
        """Feed statistics with the bytes moved since the last tick; sample speed history."""
        elapsed = 0.0 if self._last_tick is None else min(5.0, now - self._last_tick)
        self._last_tick = now
        any_active = False
        sample = now - self._last_sample >= 1.0
        if sample:
            self._last_sample = now
        for d in list(self.downloads.values()):
            seen = self._seen_bytes.get(d.id)
            cur = d.downloaded
            if seen is None:
                self._seen_bytes[d.id] = cur          # existing progress was counted earlier
            elif cur != seen:
                delta = cur - seen if cur > seen else 0
                self._seen_bytes[d.id] = cur
                if delta:
                    self.stats.add_traffic(delta, net.host_of(d.url), d.category)
            if d.status in ACTIVE:
                any_active = True
                if sample:
                    d.history.append(d.speed)
            elif sample and d.history:
                d.history.clear()
        if any_active and elapsed:
            self.stats.add_active_time(elapsed)
        for did in [k for k in self._seen_bytes if k not in self.downloads]:
            self._seen_bytes.pop(did, None)

    def data_cap(self) -> dict | None:
        s = self.config.settings
        if not s.data_cap_gb:
            return None
        used, limit = self.stats.month_bytes(), s.data_cap_gb * 1024 ** 3
        return {"used": used, "limit": limit, "hit": used >= limit, "action": s.data_cap_action}

    def _check_data_cap(self) -> None:
        cap = self.data_cap()
        month = dt.datetime.now().strftime("%Y-%m")
        if not cap or not cap["hit"]:
            if self.cap_hit_month and (not cap or self.cap_hit_month != month or not cap["hit"]):
                self.cap_hit_month = None
            return
        if self.cap_hit_month == month:
            return                                    # handled once; the user may carry on
        self.cap_hit_month = month
        if cap["action"] == "pause":
            self.stop_all()

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
            self._apply_speed()
            wall = time.time()
            for d in list(self.downloads.values()):
                if d.status == ERROR and d.retry_at and wall >= d.retry_at:
                    d.retry_at = None
                    d.error = ""
                    d.status = QUEUED
                    self._dirty = True
                    self._schedule()
            self._check_when_done(wall)
            self._count_traffic(now)
            self._check_data_cap()
            if any(d.status in ACTIVE for d in self.downloads.values()):
                self._dirty = True
            if self._dirty and now - self._last_save > 2.0:
                try:
                    self.save()
                except OSError:
                    pass
            time.sleep(0.5)
