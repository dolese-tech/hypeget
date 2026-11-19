"""Register the native messaging host with Chrome, Edge, Brave and Chromium.

Runs on every app start (and from the installer with --register), so a moved
or repaired install fixes itself. Per-user only: no admin rights needed.

  Windows: manifest in %LOCALAPPDATA%\\HyperGet, plus an HKCU registry key per
           browser pointing at it.
  macOS / Linux: manifest file in each browser's NativeMessagingHosts folder.
"""
from __future__ import annotations

import json
import os
import sys

from .config import app_home

HOST_NAME = "com.dolese.hyperget"

# The extension's fixed ID (from the "key" in extension/manifest.json). Store
# IDs are added by the release build in store_ids.json once the stores
# assign them.
PINNED_EXTENSION_ID = "oeclpagllkokmfmdpapcaeljjcbndgao"

WINDOWS_KEYS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
]


def _posix_dirs() -> list[str]:
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
        rels = ["Google/Chrome", "Microsoft Edge", "BraveSoftware/Brave-Browser", "Chromium"]
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
        rels = ["google-chrome", "microsoft-edge", "BraveSoftware/Brave-Browser", "chromium"]
    return [os.path.join(base, r, "NativeMessagingHosts") for r in rels]


def extension_ids() -> list[str]:
    ids = [PINNED_EXTENSION_ID]
    path = os.path.join(os.path.dirname(__file__), "store_ids.json")
    try:
        with open(path, encoding="utf-8-sig") as f:   # tolerate a BOM from Windows tools
            data = json.load(f)
        for key in ("chrome", "edge"):
            v = str(data.get(key) or "").strip()
            if len(v) == 32 and v.isalpha() and v.islower() and v not in ids:
                ids.append(v)
    except (OSError, ValueError):
        pass
    return ids


def host_command_path() -> str:
    """The program browsers should start. Frozen build: the bundled host exe.
    From source: a small launcher script written next to the settings."""
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        exe = os.path.join(here, "HyperGet-NativeHost.exe" if os.name == "nt" else "HyperGet-NativeHost")
        if os.path.isfile(exe):
            return exe
    home = app_home()
    os.makedirs(home, exist_ok=True)
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.name == "nt":
        path = os.path.join(home, "native-host.bat")
        body = (f'@echo off\r\nset "PYTHONPATH={pkg_parent};%PYTHONPATH%"\r\n'
                f'"{sys.executable}" -m hypeget.native_host %*\r\n')
    else:
        path = os.path.join(home, "native-host.sh")
        body = (f'#!/bin/sh\nexport PYTHONPATH="{pkg_parent}${{PYTHONPATH:+:$PYTHONPATH}}"\n'
                f'export HYPEGET_HOME="{home}"\nexec "{sys.executable}" -m hypeget.native_host "$@"\n')
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(body)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def manifest(host_path: str) -> dict:
    return {
        "name": HOST_NAME,
        "description": "HyperGet Downloader browser integration",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{i}/" for i in extension_ids()],
    }


def register(extra_dirs: list[str] | None = None) -> list[str]:
    """Write the host manifest where browsers look for it. Returns the places written."""
    host = host_command_path()
    data = json.dumps(manifest(host), indent=2)
    written: list[str] = []
    if os.name == "nt":
        folder = os.path.join(os.environ.get("LOCALAPPDATA") or app_home(), "HyperGet")
        os.makedirs(folder, exist_ok=True)
        mpath = os.path.join(folder, HOST_NAME + ".json")
        with open(mpath, "w", encoding="utf-8") as f:
            f.write(data)
        written.append(mpath)
        import winreg  # type: ignore[import-not-found]
        for key in WINDOWS_KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + "\\" + HOST_NAME) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, mpath)
            written.append("HKCU\\" + key + "\\" + HOST_NAME)
    else:
        for d in _posix_dirs():
            parent = os.path.dirname(d)
            if not os.path.isdir(parent):      # browser not installed
                continue
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, HOST_NAME + ".json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(data)
            written.append(p)
    for d in extra_dirs or []:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, HOST_NAME + ".json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(data)
        written.append(p)
    return written


def unregister() -> None:
    if os.name == "nt":
        import winreg  # type: ignore[import-not-found]
        for key in WINDOWS_KEYS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key + "\\" + HOST_NAME)
            except OSError:
                pass
        folder = os.path.join(os.environ.get("LOCALAPPDATA") or app_home(), "HyperGet")
        try:
            os.remove(os.path.join(folder, HOST_NAME + ".json"))
        except OSError:
            pass
    else:
        for d in _posix_dirs():
            try:
                os.remove(os.path.join(d, HOST_NAME + ".json"))
            except OSError:
                pass
