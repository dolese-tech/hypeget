"""Clipboard watching, like IDM: copy a download link anywhere and HyperGet offers it.

Only acts on a single http(s) link that points to a file, a stream or a video
site page, and never on something already in the download list.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import urllib.parse
from typing import Callable

from .engine.categories import _EXT

_URL = re.compile(r"^https?://[^\s<>\"']{4,2000}$", re.I)
_FILE_EXTS = (set().union(*_EXT.values()) | {"m3u8"}) - {"ts", "txt", "sh", "bin"}


def get_text() -> str | None:
    """Current clipboard text (Windows). None where unsupported or empty."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes
    CF_UNICODETEXT = 13
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not user32.OpenClipboard(None):
        return None                       # another program is using it; try next time
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)[:4096]
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def downloadable_link(text: str | None, supports_site: Callable[[str], bool] = lambda u: False) -> str | None:
    """The link to offer, or None. A file/stream extension or a known video site qualifies."""
    if not text:
        return None
    text = text.strip()
    if not _URL.match(text):
        return None
    path = urllib.parse.urlparse(text).path.lower()
    ext = os.path.splitext(path)[1].lstrip(".")
    if ext in _FILE_EXTS:
        return text
    try:
        return text if supports_site(text) else None
    except Exception:  # noqa: BLE001
        return None


class ClipboardWatcher:
    def __init__(self, on_link: Callable[[str], None], is_known: Callable[[str], bool],
                 enabled: Callable[[], bool], read: Callable[[], str | None] = get_text,
                 supports_site: Callable[[str], bool] = lambda u: False, interval: float = 1.0):
        self.on_link, self.is_known, self.enabled = on_link, is_known, enabled
        self.read, self.supports_site, self.interval = read, supports_site, interval
        self._stop = threading.Event()
        self._last: str | None = None

    def prime(self) -> None:
        """Remember what's on the clipboard now, so starting HyperGet doesn't pop it up."""
        try:
            self._last = self.read()
        except Exception:  # noqa: BLE001
            self._last = None

    def poll(self) -> str | None:
        """One check; returns the link it offered, if any."""
        try:
            text = self.read()
        except Exception:  # noqa: BLE001
            return None
        if text == self._last:
            return None
        self._last = text
        if not self.enabled():
            return None
        link = downloadable_link(text, self.supports_site)
        if not link or self.is_known(link):
            return None
        self.on_link(link)
        return link

    def start(self) -> None:
        self.prime()

        def loop():
            while not self._stop.wait(self.interval):
                self.poll()

        threading.Thread(target=loop, daemon=True, name="clipboard").start()

    def stop(self) -> None:
        self._stop.set()
