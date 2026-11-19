"""Notification-area (system tray) icon, like IDM's.

Closing the window keeps HyperGet running here, so the browser extension and
scheduled downloads keep working. The icon's tooltip shows live speed, its
menu has the everyday actions, and a pop-up says when a download finishes.

``TrayController`` holds the logic and works with any backend; ``PystrayBackend``
draws the real icon with pystray. pystray is imported lazily because it fails
on systems without a desktop (it raises, not just ImportError).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Callable

SPEEDS = [(0, "Unlimited"), (512 * 1024, "512 KB/s"), (1024 ** 2, "1 MB/s"),
          (2 * 1024 ** 2, "2 MB/s"), (5 * 1024 ** 2, "5 MB/s"), (10 * 1024 ** 2, "10 MB/s")]
ICON_PATH = os.path.join(os.path.dirname(__file__), "ui", "icons", "tray.png")


def human_speed(bps: float) -> str:
    if bps >= 1024 ** 2:
        return f"{bps / 1024 ** 2:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


@dataclass
class MenuItem:
    label: str
    action: Callable[[], None] | None = None
    default: bool = False                       # double-click / left-click
    checked: Callable[[], bool] | None = None
    submenu: list = field(default_factory=list)
    separator: bool = False


class TrayController:
    """Menu, tooltip and notifications for the tray, independent of the GUI toolkit."""

    def __init__(self, manager, show: Callable[[], None], command: Callable[[str], None],
                 quit_app: Callable[[], None], notify_enabled: Callable[[], bool] = lambda: True):
        self.manager = manager
        self.show = show
        self.command = command          # run a UI command in the window, e.g. "add"
        self.quit_app = quit_app
        self.notify_enabled = notify_enabled
        self._seen: dict[str, str] = {}
        self._primed = False

    # ---- menu --------------------------------------------------------
    def menu(self) -> list[MenuItem]:
        m = self.manager

        def speed_item(bps: int, label: str) -> MenuItem:
            return MenuItem(label, lambda: m.set_speed_limit(bps),
                            checked=lambda: m.config.settings.speed_limit == bps)

        return [
            MenuItem("Open HyperGet", self.show, default=True),
            MenuItem("Add URL…", lambda: (self.show(), self.command("add"))),
            MenuItem("", separator=True),
            MenuItem("Start queue", m.start_queue),
            MenuItem("Stop all", m.stop_all),
            MenuItem("Speed limit", submenu=[speed_item(b, l) for b, l in SPEEDS]),
            MenuItem("", separator=True),
            MenuItem("Exit", self.quit_app),
        ]

    # ---- tooltip -----------------------------------------------------
    def tooltip(self, snap: dict | None = None) -> str:
        snap = snap or self.manager.snapshot()
        active, waiting = snap["active"], snap["waiting"]
        if not active:
            return "HyperGet · " + (f"{waiting} waiting" if waiting else "idle")
        return f"HyperGet · {active} active · {human_speed(snap['total_speed'])}"

    # ---- notifications -----------------------------------------------
    def changes(self, snap: dict | None = None) -> list[tuple[str, str]]:
        """(title, message) pop-ups for downloads that finished or failed since last call."""
        snap = snap or self.manager.snapshot()
        out: list[tuple[str, str]] = []
        current = {}
        for d in snap["downloads"]:
            current[d["id"]] = d["status"]
            before = self._seen.get(d["id"])
            if not self._primed or before == d["status"]:
                continue
            if d["status"] == "complete" and before is not None:
                out.append(("Download complete", d["filename"]))
            elif d["status"] == "error" and before is not None:
                out.append(("Download failed", f"{d['filename']}: {d['error']}"))
        self._seen = current
        self._primed = True
        return out if self.notify_enabled() else []


class PystrayBackend:
    """Draws the TrayController with pystray. ``start()`` returns False when no
    tray is possible here (no desktop, pystray missing); HyperGet then simply
    quits when its window closes."""

    def __init__(self, ctl: TrayController, interval: float = 1.5):
        self.ctl = ctl
        self.interval = interval
        self.icon = None
        self.error: str = ""            # why the tray isn't available, for diagnostics
        self._stop = threading.Event()

    def start(self) -> bool:
        try:
            import pystray  # noqa: PLC0415 - optional, and fails without a desktop
            from PIL import Image
        except Exception as e:  # noqa: BLE001
            self.error = f"pystray unavailable: {e}"
            return False
        try:
            image = Image.open(ICON_PATH)
            self.icon = pystray.Icon("HyperGet", image, "HyperGet", self._to_pystray(pystray, self.ctl.menu()))
            # Our own daemon thread (not run_detached): the icon's loop must never keep
            # the process alive after the user chooses Exit.
            threading.Thread(target=self.icon.run, kwargs={"setup": self._setup}, daemon=True,
                             name="tray-icon").start()
        except Exception as e:  # noqa: BLE001
            self.error = f"tray failed: {e}"
            self.icon = None
            return False
        threading.Thread(target=self._update_loop, daemon=True, name="tray").start()
        return True

    @staticmethod
    def _action(fn):
        def run(icon, item):
            fn()
        return run

    @staticmethod
    def _checked(fn):
        def checked(item):
            return bool(fn())
        return checked

    @staticmethod
    def _setup(icon) -> None:
        icon.visible = True

    def _to_pystray(self, pystray, items: list[MenuItem]):
        out = []
        for it in items:
            if it.separator:
                out.append(pystray.Menu.SEPARATOR)
            elif it.submenu:
                out.append(pystray.MenuItem(it.label, pystray.Menu(*self._to_pystray(pystray, it.submenu))))
            else:
                # pystray checks callback signatures: exactly (icon, item) and (item).
                kwargs = {"default": it.default}
                if it.checked:
                    kwargs["checked"] = self._checked(it.checked)
                    kwargs["radio"] = True
                out.append(pystray.MenuItem(it.label, self._action(it.action), **kwargs))
        return out

    def _update_loop(self):
        while not self._stop.wait(self.interval):
            try:
                snap = self.ctl.manager.snapshot()
                self.icon.title = self.ctl.tooltip(snap)
                for title, msg in self.ctl.changes(snap):
                    try:
                        self.icon.notify(msg, title)
                    except Exception:  # noqa: BLE001 - notifications unsupported on this desktop
                        pass
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        self._stop.set()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:  # noqa: BLE001
                pass
