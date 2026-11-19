"""The Download record shared by the engine, persistence and UI."""
from __future__ import annotations

import collections
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

from .categories import badge, category_for

# Statuses
QUEUED = "queued"
CONNECTING = "connecting"
DOWNLOADING = "downloading"
MERGING = "merging"
PAUSED = "paused"
COMPLETE = "complete"
ERROR = "error"

ACTIVE = {CONNECTING, DOWNLOADING, MERGING}
UNFINISHED = {QUEUED, CONNECTING, DOWNLOADING, MERGING, PAUSED, ERROR}


@dataclass
class Download:
    url: str
    save_dir: str
    kind: str = "http"                 # http | hls | site
    filename: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    page_url: str = ""                 # page the extension found it on
    title: str = ""                    # human title (videos)
    quality: str = ""                  # e.g. "1080p"
    options: dict = field(default_factory=dict)   # kind-specific (variant url, format id, ...)
    headers: dict = field(default_factory=dict)   # cookie/referer forwarded by the extension
    size: int | None = None
    downloaded: int = 0
    status: str = QUEUED
    error: str = ""
    resumable: bool | None = None
    max_connections: int = 8
    segments: list = field(default_factory=list)  # [[start, end, pos], ...] inclusive end
    parts_total: int = 0               # HLS: number of media segments
    parts_done: int = 0
    added: float = field(default_factory=time.time)
    finished_at: float | None = None
    in_queue: bool = True
    probed: bool = False
    filename_locked: bool = False      # user picked the name; don't replace from server
    retries: int = 0                   # automatic retries used so far
    retry_at: float | None = None      # wall-clock time of the next automatic retry

    # Runtime-only (not persisted)
    speed: float = field(default=0.0, compare=False)
    eta: float | None = field(default=None, compare=False)
    connections: list = field(default_factory=list, compare=False)  # live per-connection %

    _RUNTIME = ("speed", "eta", "connections")

    def __post_init__(self):
        self._lock = threading.RLock()
        self._samples: collections.deque = collections.deque(maxlen=40)

    # ---- derived ---------------------------------------------------------
    @property
    def lock(self):
        return self._lock

    @property
    def target_path(self) -> str:
        return os.path.join(self.save_dir, self.filename or "download")

    @property
    def category(self) -> str:
        return category_for(self.filename or self.url, self.kind)

    @property
    def progress(self) -> float:
        if self.status == COMPLETE:
            return 1.0
        if self.kind == "hls" and self.parts_total:
            return self.parts_done / self.parts_total
        if self.size:
            return min(1.0, self.downloaded / self.size)
        return 0.0

    def update_speed(self, now: float | None = None) -> None:
        """Rolling ~4s average; ETA derived from it. Called by the manager tick."""
        now = now or time.monotonic()
        self._samples.append((now, self.downloaded))
        while len(self._samples) > 2 and now - self._samples[0][0] > 4.0:
            self._samples.popleft()
        if self.status not in ACTIVE or len(self._samples) < 2:
            self.speed, self.eta = 0.0, None
            return
        (t0, b0), (t1, b1) = self._samples[0], self._samples[-1]
        self.speed = max(0.0, (b1 - b0) / (t1 - t0)) if t1 > t0 else 0.0
        total = self.estimated_total()
        if self.speed > 0 and total:
            self.eta = max(0.0, (total - self.downloaded) / self.speed)
        else:
            self.eta = None

    def reset_speed(self) -> None:
        self._samples.clear()
        self.speed, self.eta = 0.0, None

    def estimated_total(self) -> int | None:
        if self.size:
            return self.size
        if self.kind == "hls" and self.parts_total and self.parts_done:
            return int(self.downloaded / self.parts_done * self.parts_total)
        return None

    # ---- serialisation ---------------------------------------------------
    def to_state(self) -> dict:
        d = asdict(self)
        for k in self._RUNTIME:
            d.pop(k, None)
        return d

    @classmethod
    def from_state(cls, d: dict) -> "Download":
        known = {k for k in cls.__dataclass_fields__ if k not in cls._RUNTIME}
        dl = cls(**{k: v for k, v in d.items() if k in known})
        if dl.status in ACTIVE:
            dl.status = PAUSED if dl.downloaded else QUEUED
        return dl

    def to_view(self) -> dict:
        """What the UI needs."""
        from .net import host_of
        return {
            "id": self.id,
            "url": self.url,
            "page_url": self.page_url,
            "kind": self.kind,
            "filename": self.filename,
            "title": self.title,
            "quality": self.quality,
            "badge": badge(self.filename or self.url, self.kind),
            "host": host_of(self.url),
            "category": self.category,
            "size": self.estimated_total(),
            "size_exact": self.size is not None,
            "downloaded": self.downloaded,
            "progress": self.progress,
            "status": self.status,
            "error": self.error,
            "resumable": self.resumable,
            "speed": self.speed,
            "eta": self.eta,
            "connections": list(self.connections),
            "max_connections": self.max_connections,
            "parts_total": self.parts_total,
            "parts_done": self.parts_done,
            "save_dir": self.save_dir,
            "path": self.target_path,
            "added": self.added,
            "finished_at": self.finished_at,
            "in_queue": self.in_queue,
            "retries": self.retries,
            "retry_in": max(0, round(self.retry_at - time.time())) if self.retry_at else None,
        }


def unique_path(directory: str, filename: str, own: str | None = None) -> str:
    """Pick a filename in ``directory`` that doesn't clash with an existing file."""
    base, ext = os.path.splitext(filename)
    if base.lower().endswith(".tar"):
        base, ext = base[:-4], ".tar" + ext
    candidate, n = filename, 1
    while True:
        full = os.path.join(directory, candidate)
        if full == own or not (os.path.exists(full) or os.path.exists(full + ".part")):
            return candidate
        n += 1
        candidate = f"{base} ({n}){ext}"
