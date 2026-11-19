"""User settings, stored as JSON in ~/.hypeget (override with HYPEGET_HOME)."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field


def app_home() -> str:
    return os.environ.get("HYPEGET_HOME") or os.path.join(os.path.expanduser("~"), ".hypeget")


def default_download_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads")


@dataclass
class Settings:
    download_dir: str = field(default_factory=default_download_dir)
    file_by_category: bool = True        # Downloads/Compressed, Downloads/Video ...
    connections: int = 8                 # per download
    max_active: int = 3                  # downloads running at once (queue)
    speed_limit: int = 2 * 1024 * 1024   # bytes/s, 0 = unlimited
    scheduler_enabled: bool = False
    scheduler_start: str = "02:00"
    scheduler_stop: str = "07:00"
    api_port: int = 52817                # preferred local API port (the browser helper finds it either way)
    theme: str = "light"
    close_to_tray: bool = True           # closing the window keeps HyperGet in the notification area
    notify_complete: bool = True         # pop-up when a download finishes or fails
    auto_retry: int = 3                  # retries for downloads that fail on a network problem (0 = off)
    retry_delay: int = 30                # seconds before the first retry; doubles each time
    speed_rule_enabled: bool = False     # a different speed limit during part of the day
    speed_rule_start: str = "08:00"
    speed_rule_end: str = "17:00"
    speed_rule_limit: int = 1024 * 1024  # bytes/s during the rule window (0 = unlimited)
    clipboard_watch: bool = True         # offer links copied anywhere, like IDM
    when_done: str = "nothing"           # nothing | sleep | shutdown | exit - runs once, then resets


class Config:
    def __init__(self, home: str | None = None):
        self.home = home or app_home()
        os.makedirs(self.home, exist_ok=True)
        self.path = os.path.join(self.home, "settings.json")
        self._lock = threading.Lock()
        self.settings = Settings()
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        known = Settings.__dataclass_fields__
        for k, v in data.items():
            if k in known:
                setattr(self.settings, k, v)

    def save(self) -> None:
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self.settings), f, indent=2)
            os.replace(tmp, self.path)

    def update(self, **changes) -> Settings:
        known = Settings.__dataclass_fields__
        for k, v in changes.items():
            if k not in known:
                continue
            cur = getattr(self.settings, k)
            if isinstance(cur, bool):
                v = bool(v)
            elif isinstance(cur, int):
                v = int(v)
            elif isinstance(cur, str):
                v = str(v)
            setattr(self.settings, k, v)
        s = self.settings
        s.connections = max(1, min(32, s.connections))
        s.max_active = max(1, min(20, s.max_active))
        s.speed_limit = max(0, s.speed_limit)
        s.speed_rule_limit = max(0, s.speed_rule_limit)
        s.auto_retry = max(0, min(10, s.auto_retry))
        s.retry_delay = max(5, min(3600, s.retry_delay))
        if s.when_done not in ("nothing", "sleep", "shutdown", "exit"):
            s.when_done = "nothing"
        self.save()
        return s

    def to_dict(self) -> dict:
        return asdict(self.settings)
