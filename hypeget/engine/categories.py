"""Map file extensions to the sidebar categories."""
from __future__ import annotations

import os

CATEGORIES = ["Compressed", "Documents", "Music", "Programs", "Video"]

_EXT = {
    "Compressed": {"zip", "rar", "7z", "gz", "tgz", "bz2", "xz", "tar", "iso", "img", "zst"},
    "Documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub", "odt", "csv", "rtf"},
    "Music": {"mp3", "flac", "wav", "aac", "m4a", "ogg", "opus", "wma"},
    "Programs": {"exe", "msi", "dmg", "pkg", "deb", "rpm", "apk", "appimage", "bin", "sh"},
    "Video": {"mp4", "mkv", "webm", "avi", "mov", "m4v", "flv", "wmv", "ts", "m3u8", "mpd"},
}


def extension(filename: str) -> str:
    name = filename.lower()
    for double in (".tar.gz", ".tar.xz", ".tar.bz2"):
        if name.endswith(double):
            return name.rsplit(".", 1)[1]
    return os.path.splitext(name)[1].lstrip(".")


def badge(filename: str, kind: str = "http") -> str:
    """Short label shown in the file-type badge (ISO, MP4, HLS ...)."""
    if kind == "hls":
        return "HLS"
    ext = extension(filename)
    return (ext[:4] or "FILE").upper()


def category_for(filename: str, kind: str = "http") -> str:
    if kind in ("hls", "site"):
        return "Video"
    ext = extension(filename)
    for cat, exts in _EXT.items():
        if ext in exts:
            return cat
    return "Other"
