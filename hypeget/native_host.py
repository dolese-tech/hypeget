"""Native messaging host: the small helper Chrome/Edge start for the extension.

The browser launches this program and talks to it over stdin/stdout using the
native messaging framing (4-byte little-endian length + UTF-8 JSON). Each
request from the extension

    {"id": 7, "method": "POST", "path": "/api/downloads", "body": {...}}

is forwarded to the running HyperGet app and answered with

    {"id": 7, "ok": true, "status": 201, "data": {...}}

If HyperGet isn't running, the host starts it (like IDM) and waits for it.
Special request: {"id": 1, "method": "HELLO", "launch": false} reports
whether the app is running without starting it.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import __version__
from .config import app_home

MAX_MESSAGE = 1024 * 1024          # browser -> host limit we accept
LAUNCH_WAIT = 20.0                 # seconds to wait for a freshly started app
ALLOWED_PREFIX = "/api/"


# ---------------------------------------------------------------- framing
def read_message(stream) -> dict | None:
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    if length > MAX_MESSAGE:
        raise ValueError("message too large")
    data = stream.read(length)
    if len(data) < length:
        return None
    return json.loads(data.decode("utf-8"))


def write_message(stream, msg: dict) -> None:
    data = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("<I", len(data)))
    stream.write(data)
    stream.flush()


# ---------------------------------------------------------------- the app
def runtime_path() -> str:
    return os.path.join(app_home(), "runtime.json")


def app_port() -> int | None:
    """Port of the running app, or None if it isn't running."""
    try:
        with open(runtime_path(), encoding="utf-8") as f:
            port = int(json.load(f)["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{port}/api/ping", headers={"X-HyperGet": "1"}), timeout=2) as r:
            if json.loads(r.read()).get("app") == "hyperget":
                return port
    except (OSError, ValueError):
        pass
    return None


def app_command() -> list[str]:
    """How to start HyperGet from here. HYPEGET_APP_ARGS adds arguments
    (tests use "--headless" because there is no screen)."""
    extra = os.environ.get("HYPEGET_APP_ARGS", "").split()
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        for name in ("HyperGet.exe", "HyperGet"):
            exe = os.path.join(here, name)
            if os.path.isfile(exe):
                return [exe, *extra]
    return [sys.executable, "-m", "hypeget", *extra]


def launch_app() -> int | None:
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(app_command(), **kwargs)  # noqa: S603
    end = time.monotonic() + LAUNCH_WAIT
    while time.monotonic() < end:
        port = app_port()
        if port:
            return port
        time.sleep(0.25)
    return None


def forward(port: int, method: str, path: str, body) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                 headers={"X-HyperGet": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:200]}


# ---------------------------------------------------------------- loop
def handle(msg: dict, state: dict) -> dict:
    mid = msg.get("id")
    method = str(msg.get("method", "GET")).upper()
    if method == "HELLO":
        port = app_port()
        if not port and msg.get("launch"):
            port = launch_app()
        state["port"] = port
        return {"id": mid, "ok": True, "status": 200,
                "data": {"host": __version__, "app_running": bool(port)}}

    path = str(msg.get("path", ""))
    if not path.startswith(ALLOWED_PREFIX) or ".." in path or method not in ("GET", "POST", "DELETE"):
        return {"id": mid, "ok": False, "status": 400, "data": {"error": "bad request"}}

    port = state.get("port") or app_port()
    if not port:
        port = launch_app()
        if not port:
            return {"id": mid, "ok": False, "status": 503, "data": {"error": "HyperGet could not be started"}}
    state["port"] = port
    try:
        status, data = forward(port, method, path, msg.get("body"))
    except OSError:
        # App closed since last call: start it again once.
        state["port"] = None
        port = launch_app()
        if not port:
            return {"id": mid, "ok": False, "status": 503, "data": {"error": "HyperGet is not running"}}
        state["port"] = port
        status, data = forward(port, method, path, msg.get("body"))
    return {"id": mid, "ok": 200 <= status < 300, "status": status, "data": data}


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    state: dict = {"port": None}
    while True:
        try:
            msg = read_message(stdin)
        except (ValueError, json.JSONDecodeError):
            write_message(stdout, {"id": None, "ok": False, "status": 400, "data": {"error": "bad message"}})
            continue
        if msg is None:          # browser closed the pipe
            return
        try:
            reply = handle(msg, state)
        except Exception as e:  # noqa: BLE001 - never die on one bad request
            reply = {"id": msg.get("id"), "ok": False, "status": 500, "data": {"error": str(e)}}
        write_message(stdout, reply)


if __name__ == "__main__":
    main()
