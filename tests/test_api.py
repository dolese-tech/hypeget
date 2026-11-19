import json
import urllib.error
import urllib.request

import pytest
from conftest import wait_for

from hypeget.engine import grabber
from hypeget.server import ApiServer


@pytest.fixture
def api(manager):
    s = ApiServer(manager, 0).start()
    yield s
    s.stop()


def call(api, method, path, body=None, headers=None):
    h = {"X-HyperGet": "1", "Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(api.url.rstrip("/") + path, method=method, headers=h,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_requires_header(api):
    code, _ = call(api, "GET", "/api/state", headers={"X-HyperGet": ""})
    assert code == 400


def test_blocks_websites_allows_extensions(api):
    assert call(api, "GET", "/api/state", headers={"Origin": "https://evil.example"})[0] == 403
    assert call(api, "GET", "/api/state", headers={"Origin": "chrome-extension://abcdef"})[0] == 200
    assert call(api, "GET", "/api/state", headers={"Host": f"attacker.test:{api.port}"})[0] == 403


def test_static_ui(api):
    with urllib.request.urlopen(api.url) as r:
        assert b"HyperGet Downloader" in r.read()
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(api.url + "../../etc/passwd")


def test_add_and_state(api, manager, server):
    code, res = call(api, "POST", "/api/downloads", {"url": server + "/file.bin"})
    assert code == 201
    did = res["downloads"][0]["id"]
    wait_for(manager.get(did))
    code, st = call(api, "GET", "/api/state")
    d = next(x for x in st["downloads"] if x["id"] == did)
    assert d["status"] == "complete" and st["counts"]["finished"] == 1


def test_inspect_hls_and_quality_download(api, manager, server):
    code, info = call(api, "POST", "/api/inspect", {"url": server + "/hls/master.m3u8"})
    assert code == 200 and info["kind"] == "hls"
    opt = info["options"][2]
    code, res = call(api, "POST", "/api/downloads", {
        "url": server + "/hls/master.m3u8", "kind": "hls", "quality": opt["quality"],
        "options": {"variant_url": opt["variant_url"], "audio_url": opt["audio_url"]}})
    dl = manager.get(res["downloads"][0]["id"])
    wait_for(dl)
    assert dl.status == "complete" and dl.quality == "360p"


def test_rejects_non_http(api):
    code, res = call(api, "POST", "/api/downloads", {"url": "file:///etc/passwd"})
    assert code == 400


def test_settings_and_delete(api, manager, server):
    code, s = call(api, "POST", "/api/settings", {"max_active": 99, "connections": 4})
    assert s["max_active"] == 20 and s["connections"] == 4
    _, res = call(api, "POST", "/api/downloads", {"url": server + "/file.bin", "start": False})
    did = res["downloads"][0]["id"]
    assert call(api, "DELETE", f"/api/downloads/{did}")[0] == 200
    assert manager.get(did) is None


def test_grabber(server, monkeypatch):
    html = f'<a href="/file.zip">x</a><img src="a.png"><a href="{server}/doc.pdf">d</a> {server}/v/master.m3u8'
    monkeypatch.setattr("hypeget.engine.net.fetch_text", lambda u, h=None: (html, server + "/page/"))
    links = grabber.grab(server + "/page/")
    names = [x["filename"] for x in links]
    assert names == ["file.zip", "doc.pdf", "master.m3u8"]
    assert links[2]["badge"] == "HLS"
