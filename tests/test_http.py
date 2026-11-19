import os
import time

from conftest import FILE, H, wait_for

from hypeget.engine import net
from hypeget.engine.download import Download, unique_path


def test_probe_range(server):
    p = net.probe(server + "/file.bin")
    assert p.size == len(FILE) and p.resumable and p.filename == "file.bin"


def test_probe_no_range(server):
    p = net.probe(server + "/norange.bin")
    assert p.size == len(FILE) and not p.resumable


def test_probe_disposition_and_redirect(server):
    assert net.probe(server + "/named").filename == "report Q3.pdf"
    assert net.probe(server + "/redirect").url.endswith("/file.bin")


def test_segmented_download(manager, server):
    dl = manager.add(server + "/file.bin")
    assert dl.filename == "file.bin"            # name shown before connecting
    wait_for(dl)
    assert dl.status == "complete", dl.error
    assert dl.save_dir.endswith("Other") or os.path.isdir(dl.save_dir)
    with open(dl.target_path, "rb") as f:
        assert f.read() == FILE
    assert not os.path.exists(dl.target_path + ".part")


def test_category_folder(manager, server):
    dl = manager.add(server + "/named")
    wait_for(dl)
    assert dl.status == "complete"
    assert os.path.basename(dl.save_dir) == "Documents"
    assert dl.filename == "report Q3.pdf"


def test_no_range_download(manager, server):
    dl = manager.add(server + "/norange.bin")
    wait_for(dl)
    assert dl.status == "complete" and dl.resumable is False
    assert open(dl.target_path, "rb").read() == FILE


def test_error_status(manager, server):
    dl = manager.add(server + "/missing.bin")
    wait_for(dl)
    assert dl.status == "error" and "404" in dl.error


def test_pause_resume(manager, server):
    H.delay = 0.01
    dl = manager.add(server + "/slow.bin", connections=4)
    end = time.time() + 10
    while dl.downloaded < 300_000 and time.time() < end:
        time.sleep(0.02)
    manager.pause(dl.id)
    wait_for(dl, ("paused",))
    got = dl.downloaded
    assert 0 < got < len(FILE)
    assert len(dl.segments) >= 4
    H.delay = 0.0
    manager.resume(dl.id)
    wait_for(dl)
    assert dl.status == "complete"
    assert open(dl.target_path, "rb").read() == FILE


def test_resume_after_restart(home, tmp_path, server):
    from hypeget.config import Config
    from hypeget.engine.manager import Manager
    cfg = Config(str(home))
    cfg.update(download_dir=str(tmp_path / "dl"), speed_limit=0)
    H.delay = 0.01
    m = Manager(cfg)
    dl = m.add(server + "/slow.bin")
    while dl.downloaded < 200_000:
        time.sleep(0.02)
    m.shutdown()                       # simulates closing the app mid-download
    assert dl.status == "paused"
    H.delay = 0.0
    m2 = Manager(Config(str(home)))
    dl2 = m2.get(dl.id)
    assert dl2 is not None and dl2.downloaded > 0
    m2.resume(dl2.id)
    wait_for(dl2)
    assert open(dl2.target_path, "rb").read() == FILE
    m2.shutdown()


def test_unique_path(tmp_path):
    (tmp_path / "a.zip").write_bytes(b"x")
    assert unique_path(str(tmp_path), "a.zip") == "a (2).zip"
    (tmp_path / "b.tar.gz").write_bytes(b"x")
    assert unique_path(str(tmp_path), "b.tar.gz") == "b (2).tar.gz"


def test_eta_not_zero_midway():
    """Regression: old build showed 0s left at 90%."""
    dl = Download(url="http://x/f", save_dir="/tmp", size=100_000_000)
    dl.status = "downloading"
    t = 1000.0
    for i in range(5):
        dl.downloaded = 90_000_000 + i * 1_000_000
        dl.update_speed(t + i)
    assert dl.speed == 1_000_000
    assert 5 <= dl.eta <= 7
