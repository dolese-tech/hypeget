"""User settings, stored as JSON in ~/.hypeget (override with HYPEGET_HOME)."""
from __future__ import annotations

import json
import os
import re
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
    # Speed rules: a different limit on chosen days and hours. The first rule that matches wins.
    # [{"name", "enabled", "days": [0..6, Monday = 0], "start": "08:00", "end": "17:00", "limit": bytes/s}]
    speed_rules: list = field(default_factory=list)
    data_cap_gb: int = 0                 # monthly data cap in GB (0 = off)
    data_cap_action: str = "pause"       # pause | warn - when the cap is reached
    clipboard_watch: bool = True         # offer links copied anywhere, like IDM
    when_done: str = "nothing"           # nothing | sleep | shutdown | exit - runs once, then resets


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def clean_rules(rules) -> list:
    """Keep only well-formed speed rules (at most 10)."""
    out = []
    for r in rules if isinstance(rules, list) else []:
        if not isinstance(r, dict):
            continue
        start, end = str(r.get("start", "")), str(r.get("end", ""))
        if not (_HHMM.match(start) and _HHMM.match(end)):
            continue
        days = sorted({int(d) for d in r.get("days", []) if str(d).isdigit() and 0 <= int(d) <= 6})
        try:
            limit = max(0, int(r.get("limit", 0)))
        except (TypeError, ValueError):
            continue
        out.append({"name": str(r.get("name") or "Speed rule")[:40], "enabled": bool(r.get("enabled", True)),
                    "days": days, "start": start, "end": end, "limit": limit})
    return out[:10]


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
        # 0.1 had one rule as separate fields
        if "speed_rule_start" in data and not data.get("speed_rules"):
            self.settings.speed_rules = [{
                "name": "Working hours", "enabled": bool(data.get("speed_rule_enabled")), "days": list(range(7)),
                "start": data.get("speed_rule_start", "08:00"), "end": data.get("speed_rule_end", "17:00"),
                "limit": int(data.get("speed_rule_limit", 1024 * 1024))}]
        self.settings.speed_rules = clean_rules(self.settings.speed_rules)

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
            if isinstance(cur, list):
                if not isinstance(v, list):
                    continue
            elif isinstance(cur, bool):
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
        s.speed_rules = clean_rules(s.speed_rules)
        s.data_cap_gb = max(0, min(100000, s.data_cap_gb))
        if s.data_cap_action not in ("pause", "warn"):
            s.data_cap_action = "pause"
        s.auto_retry = max(0, min(10, s.auto_retry))
        s.retry_delay = max(5, min(3600, s.retry_delay))
        if s.when_done not in ("nothing", "sleep", "shutdown", "exit"):
            s.when_done = "nothing"
        self.save()
        return s

    def to_dict(self) -> dict:
        return asdict(self.settings)
