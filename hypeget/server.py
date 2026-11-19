"""Local HTTP API on 127.0.0.1, used by the app window and the browser extension.

Security: binds to loopback only, checks the Host header (DNS-rebinding) and
refuses every cross-origin request: only the app's own window (same origin)
and local programs without an Origin header, such as the native messaging
helper the browser extension talks to, are accepted. Every API call must
carry ``X-HyperGet: 1`` as well.
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .engine import grabber, media
from .engine.manager import Manager
from .engine.segments import DownloadError

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")


def open_path(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603,S607
    else:
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607


class Handler(BaseHTTPRequestHandler):
    manager: Manager
    port: int
    server_version = "HyperGet/" + __version__

    def log_message(self, *args):  # quiet
        pass

    # ---------------------------------------------------------- security
    def _origin_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin in (f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}")

    def _json(self, code: int, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > 1_000_000:
            raise ValueError("body too large")
        data = json.loads(self.rfile.read(n) or b"{}")
        return data if isinstance(data, dict) else {}

    def _api_guard(self) -> bool:
        if not self._origin_ok():
            self._json(403, {"error": "forbidden"})
            return False
        if self.headers.get("X-HyperGet") != "1":
            self._json(400, {"error": "missing X-HyperGet header"})
            return False
        return True

    # ---------------------------------------------------------- verbs
    def do_OPTIONS(self):
        # No cross-origin access is offered, so every preflight is refused.
        self.send_response(403)
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            if not self._api_guard():
                return
            return self._route("GET", path)
        if not self._origin_ok():
            self.send_error(403)
            return
        self._static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if self._api_guard():
            self._route("POST", path)

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if self._api_guard():
            self._route("DELETE", path)

    # ---------------------------------------------------------- routing
    def _route(self, method: str, path: str):
        m = self.manager
        parts = [p for p in path.split("/") if p][1:]   # drop "api"
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        try:
            if method == "GET" and parts == ["ping"]:
                return self._json(200, {"app": "hyperget", "version": __version__})
            if method == "GET" and parts == ["state"]:
                return self._json(200, m.snapshot())
            if parts == ["settings"]:
                if method == "POST":
                    return self._json(200, m.update_settings(**self._body()))
                return self._json(200, m.config.to_dict())
            if method == "POST" and parts == ["inspect"]:
                b = self._body()
                return self._json(200, media.inspect(b["url"], b.get("headers")))
            if method == "POST" and parts == ["app", "show"]:
                # Another HyperGet start (single instance) or the tray asks us to come forward.
                cmd = str(self._body().get("command") or "show")
                hook = getattr(m, "ui_show", None)
                if hook is None:
                    return self._json(409, {"error": "no window"})
                hook(cmd)
                return self._json(200, {"ok": True})
            if method == "POST" and parts == ["grab"]:
                b = self._body()
                links = grabber.grab(b["url"], b.get("headers"))
                m.grabber_projects += 1
                return self._json(200, {"links": links})
            if method == "POST" and parts == ["downloads"]:
                b = self._body()
                items = b.get("items") or [b]
                created = []
                for it in items:
                    dl = m.add(it["url"], kind=it.get("kind") or None, filename=it.get("filename") or None,
                               save_dir=it.get("save_dir") or None, quality=it.get("quality") or "",
                               options={k: v for k, v in (it.get("options") or {}).items()
                                        if k in ("variant_url", "audio_url", "format", "container")},
                               headers=it.get("headers"), title=it.get("title") or "",
                               page_url=it.get("page_url") or "", start=it.get("start", True))
                    created.append(dl.to_view())
                return self._json(201, {"downloads": created})
            if len(parts) == 3 and parts[0] == "downloads" and method == "POST":
                did, action = parts[1], parts[2]
                if action == "pause":
                    m.pause(did)
                elif action == "resume":
                    m.resume(did)
                elif action == "redownload":
                    m.redownload(did)
                elif action in ("open", "folder"):
                    dl = m.get(did)
                    if not dl:
                        return self._json(404, {"error": "not found"})
                    target = dl.target_path if action == "open" else dl.save_dir
                    if not os.path.exists(target):
                        return self._json(404, {"error": "file not found"})
                    open_path(target)
                else:
                    return self._json(404, {"error": "unknown action"})
                return self._json(200, {"ok": True})
            if len(parts) == 2 and parts[0] == "downloads" and method == "DELETE":
                m.delete(parts[1], remove_file=query.get("file") == "1")
                return self._json(200, {"ok": True})
            if method == "POST" and len(parts) == 2 and parts[0] == "actions":
                action = parts[1]
                if action == "stop_all":
                    m.stop_all()
                elif action == "start_queue":
                    m.start_queue()
                elif action == "speed_limit":
                    m.set_speed_limit(int(self._body().get("bytes_per_sec", 0)))
                else:
                    return self._json(404, {"error": "unknown action"})
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})
        except (DownloadError, ValueError, KeyError) as e:
            return self._json(400, {"error": str(e).strip("'") or e.__class__.__name__})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": str(e)})

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.realpath(os.path.join(UI_DIR, path.lstrip("/")))
        if not full.startswith(os.path.realpath(UI_DIR) + os.sep) or not os.path.isfile(full):
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".woff2"):
            ctype = "font/woff2"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


class ApiServer:
    def __init__(self, manager: Manager, port: int = 0):
        handler = type("BoundHandler", (Handler,), {"manager": manager})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        handler.port = self.httpd.server_address[1]
        self.port = handler.port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> "ApiServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
