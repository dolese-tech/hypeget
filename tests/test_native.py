"""Native messaging: framing, forwarding to the app, auto-start, registration."""
import io
import json
import os
import socket
import struct
import subprocess
import sys
import time

import pytest
from conftest import wait_for

from hypeget import native_host, native_reg
from hypeget.app import clear_runtime, write_runtime
from hypeget.server import ApiServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame(msg: dict) -> bytes:
    data = json.dumps(msg).encode()
    return struct.pack("<I", len(data)) + data


def unframe(stream) -> dict:
    (n,) = struct.unpack("<I", stream.read(4))
    return json.loads(stream.read(n))


def test_framing_roundtrip():
    buf = io.BytesIO()
    native_host.write_message(buf, {"id": 1, "x": "é"})
    buf.seek(0)
    assert native_host.read_message(buf) == {"id": 1, "x": "é"}
    assert native_host.read_message(io.BytesIO(b"")) is None


def test_oversized_message_refused():
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(struct.pack("<I", 50 * 1024 * 1024)))


def test_rejects_paths_outside_api(home):
    state = {"port": 1}
    r = native_host.handle({"id": 3, "method": "GET", "path": "/../etc"}, state)
    assert r["status"] == 400 and not r["ok"]
    r = native_host.handle({"id": 4, "method": "PUT", "path": "/api/state"}, state)
    assert r["status"] == 400


@pytest.fixture
def running_app(manager):
    s = ApiServer(manager, 0).start()
    write_runtime(s.port)
    yield s
    clear_runtime(s.port)
    s.stop()


def host_proc(home, extra_env=None):
    env = dict(os.environ, HYPEGET_HOME=str(home), PYTHONPATH=ROOT, **(extra_env or {}))
    return subprocess.Popen([sys.executable, "-m", "hypeget.native_host"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=env)


def test_host_forwards_to_running_app(home, running_app, manager, server):
    p = host_proc(home)
    try:
        p.stdin.write(frame({"id": 1, "method": "HELLO"}))
        p.stdin.flush()
        assert unframe(p.stdout)["data"]["app_running"] is True
        p.stdin.write(frame({"id": 2, "method": "POST", "path": "/api/downloads", "body": {"url": server + "/file.bin"}}))
        p.stdin.flush()
        r = unframe(p.stdout)
        assert r["id"] == 2 and r["ok"] and r["status"] == 201
        dl = manager.get(r["data"]["downloads"][0]["id"])
        wait_for(dl)
        assert dl.status == "complete"
    finally:
        p.stdin.close()
        p.wait(timeout=10)
    assert p.returncode == 0          # exits cleanly when the browser closes the pipe


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_host_starts_the_app_when_needed(home, tmp_path):
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "settings.json"), "w") as f:
        json.dump({"api_port": free_port(), "download_dir": str(tmp_path / "dl")}, f)
    p = host_proc(home, {"HYPEGET_APP_ARGS": "--headless"})
    pid = None
    try:
        p.stdin.write(frame({"id": 1, "method": "HELLO", "launch": False}))
        p.stdin.flush()
        assert unframe(p.stdout)["data"]["app_running"] is False
        t0 = time.time()
        p.stdin.write(frame({"id": 2, "method": "GET", "path": "/api/ping"}))
        p.stdin.flush()
        r = unframe(p.stdout)
        assert r["ok"] and r["data"]["app"] == "hyperget", r
        assert time.time() - t0 < native_host.LAUNCH_WAIT
        pid = json.load(open(os.path.join(home, "runtime.json")))["pid"]
    finally:
        p.stdin.close()
        p.wait(timeout=10)
        if pid:
            os.kill(pid, 15)


def test_registration_writes_runnable_host(home, tmp_path, running_app):
    target = tmp_path / "NativeMessagingHosts"
    written = native_reg.register(extra_dirs=[str(target)])
    mpath = target / "tech.dolese.hyperget.json"
    assert str(mpath) in written
    m = json.loads(mpath.read_text())
    assert m["name"] == "tech.dolese.hyperget" and m["type"] == "stdio"
    assert m["allowed_origins"] == ["chrome-extension://oeclpagllkokmfmdpapcaeljjcbndgao/"]
    assert os.access(m["path"], os.X_OK)
    # The browser runs exactly this program: talk to it like Chrome would.
    p = subprocess.Popen([m["path"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(frame({"id": 9, "method": "HELLO"}))
    p.stdin.flush()
    assert unframe(p.stdout)["data"]["app_running"] is True
    p.stdin.close()
    p.wait(timeout=10)


def test_pinned_id_matches_extension_key():
    import base64
    import hashlib
    key = json.load(open(os.path.join(ROOT, "extension", "manifest.json")))["key"]
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    assert "".join(chr(97 + int(c, 16)) for c in digest) == native_reg.PINNED_EXTENSION_ID
