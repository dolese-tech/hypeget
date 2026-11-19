"""Download statistics (Pro): data per day/month, by site and type, and the speed per hour.

Traffic is counted as it flows (the manager feeds byte deltas every tick), so the
numbers include unfinished and failed downloads, and the monthly data cap is exact.
Stored in ~/.hypeget/stats.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading

KEEP_DAYS = 400


def _day(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%d")


def _month(t: dt.datetime) -> str:
    return t.strftime("%Y-%m")


class Stats:
    def __init__(self, home: str):
        self.path = os.path.join(home, "stats.json")
        self._lock = threading.Lock()
        self.data = {"days": {}, "months": {}, "hosts": {}, "types": {}, "hours": {}}
        self.dirty = False
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            for k in self.data:
                if isinstance(loaded.get(k), dict):
                    self.data[k] = loaded[k]
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ recording
    def _dayrec(self, key: str) -> dict:
        return self.data["days"].setdefault(key, {"bytes": 0, "files": 0, "failed": 0, "seconds": 0.0})

    def add_traffic(self, nbytes: int, host: str, category: str, now: dt.datetime | None = None) -> None:
        if nbytes <= 0:
            return
        now = now or dt.datetime.now()
        with self._lock:
            self._dayrec(_day(now))["bytes"] += nbytes
            m = self.data["months"]
            m[_month(now)] = m.get(_month(now), 0) + nbytes
            h = self.data["hosts"]
            h[host] = h.get(host, 0) + nbytes
            t = self.data["types"]
            t[category] = t.get(category, 0) + nbytes
            hr = self.data["hours"].setdefault(str(now.hour), [0, 0.0])
            hr[0] += nbytes
            self.dirty = True

    def add_active_time(self, seconds: float, now: dt.datetime | None = None) -> None:
        """Time with at least one download running, for the average speed."""
        now = now or dt.datetime.now()
        with self._lock:
            self._dayrec(_day(now))["seconds"] += seconds
            self.data["hours"].setdefault(str(now.hour), [0, 0.0])[1] += seconds
            self.dirty = True

    def add_file(self, failed: bool = False, now: dt.datetime | None = None) -> None:
        now = now or dt.datetime.now()
        with self._lock:
            self._dayrec(_day(now))["failed" if failed else "files"] += 1
            self.dirty = True

    def month_bytes(self, now: dt.datetime | None = None) -> int:
        return int(self.data["months"].get(_month(now or dt.datetime.now()), 0))

    def save(self) -> None:
        with self._lock:
            days = self.data["days"]
            for k in sorted(days)[:-KEEP_DAYS]:
                days.pop(k, None)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
            self.dirty = False

    # ------------------------------------------------------------ reading
    def today(self, now: dt.datetime | None = None) -> dict:
        r = self.data["days"].get(_day(now or dt.datetime.now()), {})
        b, s = r.get("bytes", 0), r.get("seconds", 0)
        return {"bytes": b, "files": r.get("files", 0), "avg_speed": b / s if s else 0}

    def summary(self, period: str = "week", now: dt.datetime | None = None) -> dict:
        now = now or dt.datetime.now()
        days = self.data["days"]
        if period == "year":
            bars = []
            y, mo = now.year, now.month
            for _ in range(12):
                key = f"{y:04d}-{mo:02d}"
                bars.append({"label": dt.date(y, mo, 1).strftime("%b"), "bytes": self.data["months"].get(key, 0)})
                mo -= 1
                if mo == 0:
                    y, mo = y - 1, 12
            bars.reverse()
            span = 365
        else:
            span = 30 if period == "month" else 7
            bars = []
            for i in range(span - 1, -1, -1):
                d = now - dt.timedelta(days=i)
                label = d.strftime("%a") if span == 7 else d.strftime("%d")
                bars.append({"label": label, "bytes": days.get(_day(d), {}).get("bytes", 0)})
        cur = self._window(now, span)
        prev = self._window(now - dt.timedelta(days=span), span)
        hours = []
        for h in range(24):
            b, s = self.data["hours"].get(str(h), [0, 0])
            hours.append(b / s if s else 0)
        return {
            "period": period,
            "bytes": cur["bytes"], "files": cur["files"], "failed": cur["failed"],
            "avg_speed": cur["bytes"] / cur["seconds"] if cur["seconds"] else 0,
            "active_seconds": cur["seconds"],
            "change": (cur["bytes"] - prev["bytes"]) / prev["bytes"] if prev["bytes"] else None,
            "bars": bars,
            "types": sorted(self.data["types"].items(), key=lambda kv: -kv[1]),
            "hosts": sorted(self.data["hosts"].items(), key=lambda kv: -kv[1])[:6],
            "hours": hours,
            "month_bytes": self.month_bytes(now),
        }

    def _window(self, end: dt.datetime, span: int) -> dict:
        out = {"bytes": 0, "files": 0, "failed": 0, "seconds": 0.0}
        for i in range(span):
            r = self.data["days"].get(_day(end - dt.timedelta(days=i)))
            if r:
                for k in out:
                    out[k] += r.get(k, 0)
        return out
