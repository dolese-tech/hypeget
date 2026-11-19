"""Local HTTP test server with range / no-range / error / HLS endpoints."""
from __future__ import annotations

import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

FILE = os.urandom(3 * 1024 * 1024 + 12345)          # 3 MB + odd tail
SEGS = [os.urandom(40_000 + i * 997) for i in range(6)]
AUDIO = [os.urandom(9_000 + i) for i in range(6)]
KEY = bytes(range(16))


def encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    p = padding.PKCS7(128).padder()
    data = p.update(data) + p.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def media_playlist(prefix: str, n: int, key: bool = False, live: bool = False) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:4", "#EXT-X-MEDIA-SEQUENCE:0"]
    if key:
        lines.append('#EXT-X-KEY:METHOD=AES-128,URI="/hls/key.bin"')
    for i in range(n):
        lines += ["#EXTINF:4.0,", f"{prefix}{i}.ts"]
    if not live:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


MASTER = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="English",LANGUAGE="en",DEFAULT=YES,URI="audio.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2",AUDIO="aud"
v360.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2",AUDIO="aud"
v1080.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2",AUDIO="aud"
v720.m3u8
"""


PAGE = """<!doctype html><html><head><title>Demo Trailer</title></head><body style="margin:0;background:#111">
<h1 style="color:#fff;font:20px sans-serif;padding:10px">Demo video page</h1>
<video id="v" width="800" height="450" style="background:#000;display:block;margin:20px" controls></video>
<script>fetch("/hls/master.m3u8").then(r => r.text()).then(t => fetch("/hls/v720.m3u8"));</script>
</body></html>"""


class H(BaseHTTPRequestHandler):
    hits: dict = {}
    delay = 0.0

    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype="application/octet-stream", code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            step = 32 * 1024
            for i in range(0, len(body), step):
                self.wfile.write(body[i:i + step])
                if H.delay:
                    time.sleep(H.delay)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]
        H.hits[path] = H.hits.get(path, 0) + 1
        rng = self.headers.get("Range")
        if path in ("/file.bin", "/slow.bin"):
            if rng:
                m = re.match(r"bytes=(\d+)-(\d*)", rng)
                s = int(m.group(1))
                e = int(m.group(2)) if m.group(2) else len(FILE) - 1
                e = min(e, len(FILE) - 1)
                return self._send(FILE[s:e + 1], code=206,
                                  extra={"Content-Range": f"bytes {s}-{e}/{len(FILE)}", "Accept-Ranges": "bytes"})
            return self._send(FILE)
        if path == "/page.html":       # fake video site page (player loads an HLS stream)
            return self._send(PAGE.encode(), "text/html")
        if path == "/norange.bin":
            return self._send(FILE)                     # ignores Range
        if path == "/named":
            return self._send(FILE[:1000], extra={"Content-Disposition": 'attachment; filename="report Q3.pdf"'})
        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/file.bin")
            self.end_headers()
            return
        if path == "/missing.bin":
            return self._send(b"nope", code=404)
        if path == "/playlist":        # HLS without .m3u8 extension, detected by content type
            return self._send(media_playlist("/hls/v720_", 6).encode(), "application/vnd.apple.mpegurl")
        if path.startswith("/hls/"):
            name = path[5:]
            mpeg = "application/vnd.apple.mpegurl"
            if name == "master.m3u8":
                return self._send(MASTER.encode(), mpeg)
            if name in ("v360.m3u8", "v720.m3u8", "v1080.m3u8"):
                return self._send(media_playlist(name[:-5] + "_", len(SEGS)).encode(), mpeg)
            if name == "audio.m3u8":
                return self._send(media_playlist("a_", len(AUDIO)).encode(), mpeg)
            if name == "enc.m3u8":
                return self._send(media_playlist("e_", len(SEGS), key=True).encode(), mpeg)
            if name == "live.m3u8":
                return self._send(media_playlist("v720_", 3, live=True).encode(), mpeg)
            if name == "drm.m3u8":
                body = media_playlist("v720_", 3).replace(
                    "#EXT-X-MEDIA-SEQUENCE:0",
                    '#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://x",KEYFORMAT="com.apple.streamingkeydelivery"')
                return self._send(body.encode(), mpeg)
            if name == "key.bin":
                return self._send(KEY)
            m = re.match(r"(v\d+|a|e)_(\d+)\.ts$", name)
            if m:
                i = int(m.group(2))
                if m.group(1) == "a":
                    return self._send(AUDIO[i], "video/mp2t")
                if m.group(1) == "e":
                    return self._send(encrypt(SEGS[i], KEY, i.to_bytes(16, "big")), "video/mp2t")
                return self._send(SEGS[i], "video/mp2t")
        self._send(b"not found", code=404)


@pytest.fixture(scope="session")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    monkeypatch.setenv("HYPEGET_HOME", str(h))
    monkeypatch.setattr("hypeget.engine.hls.ffmpeg_path", lambda: None)
    monkeypatch.setattr("hypeget.engine.sites.ffmpeg_path", lambda: None)
    H.delay = 0.0
    return h


@pytest.fixture
def manager(home, tmp_path):
    from hypeget.config import Config
    from hypeget.engine.manager import Manager
    cfg = Config(str(home))
    cfg.update(download_dir=str(tmp_path / "dl"), speed_limit=0)
    m = Manager(cfg)
    yield m
    m.shutdown()


def wait_for(dl, statuses=("complete", "error"), timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if dl.status in statuses:
            return dl
        time.sleep(0.05)
    raise AssertionError(f"timeout; status={dl.status} error={dl.error}")
