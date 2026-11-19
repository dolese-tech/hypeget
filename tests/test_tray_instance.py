"""Single instance, the tray logic and close-to-tray window behaviour."""
import json
import os
import socket
import subprocess
import sys
import time

import pytest
from conftest import wait_for

from hypeget.app import AppWindow, write_runtime
from hypeget.instance import SingleInstance, ask_running_app
from hypeget.server import ApiServer
from hypeget.tray import MenuItem, TrayController, human_speed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- single instance
def test_only_one_instance_per_home(tmp_path):
    a, b = SingleInstance(str(tmp_path)), SingleInstance(str(tmp_path))
    assert a.acquire()
    assert not b.acquire()
    a.release()
    assert b.acquire()          # free again once the first one quits
    b.release()


def test_lock_is_freed_when_the_process_dies(tmp_path):
    code = ("import sys,time; sys.path.insert(0, %r)\n"
            "from hypeget.instance import SingleInstance\n"
            "inst = SingleInstance(%r)\nassert inst.acquire(); print('locked', flush=True); time.sleep(60)") % (ROOT, str(tmp_path))
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "locked"
    assert not SingleInstance(str(tmp_path)).acquire()
    p.kill()
    p.wait()
    s = SingleInstance(str(tmp_path))
    assert s.acquire()          # a crash never leaves a stale lock behind
    s.release()


def test_second_start_brings_the_running_one_forward(manager, home):
    shown = []
    manager.ui_show = shown.append
    s = ApiServer(manager, 0).start()
    write_runtime(s.port)
    try:
        assert ask_running_app("add", home=str(home), wait=3)
        assert ask_running_app("show", home=str(home), wait=3)
        assert shown == ["add", "show"]
    finally:
        s.stop()


def test_ask_gives_up_without_a_running_app(tmp_path):
    t0 = time.time()
    assert ask_running_app(home=str(tmp_path), wait=0.6) is False
    assert time.time() - t0 < 3


def free_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def test_second_process_exits_instead_of_running_twice(home, tmp_path):
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "settings.json"), "w") as f:
        json.dump({"api_port": free_port(), "download_dir": str(tmp_path / "dl")}, f)
    env = dict(os.environ, HYPEGET_HOME=str(home), PYTHONPATH=ROOT)
    first = subprocess.Popen([sys.executable, "-m", "hypeget", "--headless"], env=env,
                             stdout=subprocess.PIPE, text=True)
    try:
        assert "running at" in first.stdout.readline()
        second = subprocess.run([sys.executable, "-m", "hypeget", "--headless"], env=env,
                                capture_output=True, text=True, timeout=30)
        assert second.returncode == 0
        assert "already running" in second.stdout
        assert first.poll() is None          # the first one is untouched
    finally:
        first.terminate()
        first.wait(timeout=10)


# ---------------------------------------------------------------- tray logic
def flat(items):
    out = {}
    for it in items:
        if it.submenu:
            out.update({f"{it.label}/{s.label}": s for s in it.submenu})
        elif not it.separator:
            out[it.label] = it
    return out


def make_ctl(manager, calls, notify=True):
    return TrayController(manager, show=lambda: calls.append("show"),
                          command=lambda c: calls.append("cmd:" + c),
                          quit_app=lambda: calls.append("quit"), notify_enabled=lambda: notify)


def test_menu_actions(manager):
    calls = []
    ctl = make_ctl(manager, calls)
    items = flat(ctl.menu())
    assert list(items)[:4] == ["Open HyperGet", "Add URL…", "Start queue", "Stop all"]
    assert items["Open HyperGet"].default
    items["Add URL…"].action()
    items["Exit"].action()
    assert calls == ["show", "cmd:add", "quit"]
    items["Stop all"].action()
    assert manager.queue_running is False
    items["Start queue"].action()
    assert manager.queue_running is True
    items["Speed limit/1 MB/s"].action()
    assert manager.config.settings.speed_limit == 1024 ** 2
    assert items["Speed limit/1 MB/s"].checked() and not items["Speed limit/Unlimited"].checked()


def test_tooltip():
    ctl = TrayController(None, show=None, command=None, quit_app=None)
    assert ctl.tooltip({"active": 0, "waiting": 0, "total_speed": 0}) == "HyperGet · idle"
    assert ctl.tooltip({"active": 0, "waiting": 2, "total_speed": 0}) == "HyperGet · 2 waiting"
    assert ctl.tooltip({"active": 3, "waiting": 1, "total_speed": 24.2 * 1024 ** 2}) == "HyperGet · 3 active · 24.2 MB/s"
    assert human_speed(600 * 1024) == "600 KB/s"
    # Windows limits tray tooltips to 127 characters
    assert len(ctl.tooltip({"active": 99, "waiting": 0, "total_speed": 9.9e12})) < 127


def test_notifies_when_downloads_finish_or_fail(manager, server):
    calls = []
    ctl = make_ctl(manager, calls)
    assert ctl.changes() == []                          # first look only remembers
    ok = manager.add(server + "/file.bin")
    bad = manager.add(server + "/missing.bin")
    ctl.changes()                                       # sees them queued/running
    wait_for(ok)
    wait_for(bad)
    got = ctl.changes()
    assert ("Download complete", "file.bin") in got
    assert any(t == "Download failed" and "missing.bin" in m for t, m in got)
    assert ctl.changes() == []                          # each event only once


def test_no_notifications_when_switched_off(manager, server):
    ctl = make_ctl(manager, [], notify=False)
    ctl.changes()
    dl = manager.add(server + "/file.bin")
    ctl.changes()
    wait_for(dl)
    assert ctl.changes() == []


def test_old_finished_downloads_dont_notify_at_startup(manager, server):
    dl = manager.add(server + "/file.bin")
    wait_for(dl)
    ctl = make_ctl(manager, [])
    assert ctl.changes() == [] and ctl.changes() == []


# ---------------------------------------------------------------- window: close vs quit
class FakeEvent(list):
    def __iadd__(self, fn):
        self.append(fn)
        return self


class FakeWindow:
    def __init__(self, **kw):
        self.kw = kw
        self.log = []
        self.events = type("E", (), {"closing": FakeEvent()})()
        self._on_top = False

    def hide(self): self.log.append("hide")
    def show(self): self.log.append("show")
    def restore(self): self.log.append("restore")
    def destroy(self): self.log.append("destroy")
    def evaluate_js(self, js): self.log.append("js:" + js)

    @property
    def on_top(self): return self._on_top

    @on_top.setter
    def on_top(self, v): self._on_top = v


class FakeWebview:
    def create_window(self, *a, **kw):
        self.window = FakeWindow(**kw)
        return self.window


@pytest.fixture
def win(manager):
    def make(tray_up=True, hidden=False):
        return AppWindow(FakeWebview(), "http://x/", manager, tray_ok=lambda: tray_up, start_hidden=hidden)
    return make


def test_close_hides_to_tray(win, manager):
    w = win(tray_up=True)
    w.api.close()
    assert w.window.log == ["hide"]
    # Alt+F4 / taskbar close is cancelled too (returning False cancels in pywebview)
    assert w.window.events.closing[0]() is False


def test_close_quits_without_tray_or_when_turned_off(win, manager):
    w = win(tray_up=False)
    w.api.close()
    assert w.window.log == ["destroy"]
    manager.config.update(close_to_tray=False)
    w2 = win(tray_up=True)
    w2.api.close()
    assert w2.window.log == ["destroy"]


def test_exit_really_quits(win):
    w = win(tray_up=True)
    w.api.quit()
    assert w.window.log == ["destroy"]
    assert w.window.events.closing[0]() is True          # the close it triggers isn't cancelled


def test_start_hidden_and_show_with_command(win, manager):
    w = win(hidden=True)
    assert w.window.kw["hidden"] is True
    assert manager.ui_show == w.show                    # second starts reach this window
    w.show("add")
    assert w.window.log[:2] == ["show", "restore"]
    assert w.window.log[-1] == 'js:window.hgCommand && window.hgCommand("add")'


def test_unknown_commands_only_show_the_window(win):
    w = win()
    w.show("add\");alert(1);//")
    assert not any(x.startswith("js:") for x in w.window.log)
