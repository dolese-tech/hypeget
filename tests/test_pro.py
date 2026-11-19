"""Pro features in the engine: auto-retry, speed rules, 'when all downloads finish'."""
import datetime as dt
import time

from conftest import wait_for

from hypeget.engine.manager import retryable
from hypeget.engine.scheduler import in_window


def wait_until(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached")


# ---------------------------------------------------------------- auto-retry
def test_which_errors_are_retried():
    assert retryable("Timeout")
    assert retryable("Network error: [Errno 111] Connection refused")
    assert retryable("HTTP 503") and retryable("Connection closed early")
    assert not retryable("HTTP 404") and not retryable("HTTP 403")
    assert not retryable("DRM-protected stream (not supported)")
    assert not retryable("")


def test_network_failure_is_retried_until_it_works(manager, server, monkeypatch):
    manager.config.update(auto_retry=3, retry_delay=5)
    calls = {"n": 0}
    from hypeget.engine import manager as mgr
    from hypeget.engine.segments import DownloadError
    real = mgr.RUNNERS["http"]

    def flaky(dl, ctx):                       # first two attempts lose the connection
        calls["n"] += 1
        if calls["n"] <= 2:
            raise DownloadError("Timeout")
        return real(dl, ctx)

    monkeypatch.setitem(mgr.RUNNERS, "http", flaky)
    dl = manager.add(server + "/file.bin")
    wait_for(dl, ("error",))
    assert dl.retries == 1 and dl.retry_at
    assert 3 <= dl.to_view()["retry_in"] <= 5
    dl.retry_at = time.time() - 1             # fast-forward the 5 s wait
    wait_until(lambda: dl.retries == 2 and dl.status == "error" and dl.retry_at)
    assert dl.retry_at - time.time() > 5      # the delay doubles: 5 s, then 10 s
    dl.retry_at = time.time() - 1
    wait_for(dl, ("complete",))
    assert calls["n"] == 3 and dl.retries == 0 and dl.retry_at is None


def test_missing_file_is_not_retried(manager, server):
    dl = manager.add(server + "/missing.bin")
    wait_for(dl)
    time.sleep(0.6)
    assert dl.status == "error" and dl.retry_at is None and dl.retries == 0


def test_gives_up_after_the_limit(manager, server, monkeypatch):
    from hypeget.engine import manager as mgr
    from hypeget.engine.segments import DownloadError

    broken = {"on": True}
    real = mgr.RUNNERS["http"]

    def always(dl, ctx):
        if broken["on"]:
            raise DownloadError("Timeout")
        return real(dl, ctx)

    monkeypatch.setitem(mgr.RUNNERS, "http", always)
    manager.config.update(auto_retry=2, retry_delay=5)
    dl = manager.add(server + "/file.bin")
    wait_until(lambda: dl.retries == 1 and dl.retry_at)
    dl.retry_at = time.time() - 1
    wait_until(lambda: dl.retries == 2 and dl.retry_at)
    dl.retry_at = time.time() - 1
    wait_until(lambda: dl.status == "error" and dl.retry_at is None)
    time.sleep(0.6)
    assert dl.retries == 2 and dl.retry_at is None     # stays failed; Resume starts over
    broken["on"] = False                               # the network is back
    manager.resume(dl.id)
    wait_for(dl, ("complete",))
    assert dl.retries == 0


# ---------------------------------------------------------------- speed rules
def at(hhmm):
    h, m = map(int, hhmm.split(":"))
    return dt.datetime(2026, 11, 19, h, m)


def test_time_windows():
    assert in_window("08:00", "17:00", at("08:00")) and in_window("08:00", "17:00", at("16:59"))
    assert not in_window("08:00", "17:00", at("17:00")) and not in_window("08:00", "17:00", at("07:59"))
    assert in_window("22:00", "06:00", at("23:30")) and in_window("22:00", "06:00", at("05:00"))
    assert not in_window("22:00", "06:00", at("12:00"))
    assert not in_window("08:00", "08:00", at("08:00"))


WEEKDAYS = [0, 1, 2, 3, 4]


def rule(name, start, end, limit, days=WEEKDAYS, enabled=True):
    return {"name": name, "enabled": enabled, "days": days, "start": start, "end": end, "limit": limit}


def test_speed_rule_switches_the_limit(manager):
    # 2026-11-19 is a Thursday
    manager.update_settings(speed_limit=0, speed_rules=[rule("Work", "08:00", "17:00", 512 * 1024)])
    assert manager.effective_speed_limit(at("09:00")) == (512 * 1024, True)
    assert manager.effective_speed_limit(at("18:00")) == (0, False)
    manager._apply_speed(now=at("09:00"))
    assert manager.throttle.limit == 512 * 1024
    manager._apply_speed(now=at("18:00"))
    assert manager.throttle.limit == 0
    manager.update_settings(speed_rules=[rule("Work", "08:00", "17:00", 512 * 1024, enabled=False)])
    assert manager.effective_speed_limit(at("09:00")) == (0, False)


def test_rules_follow_days_and_order(manager):
    manager.update_settings(speed_limit=0, speed_rules=[
        rule("Work", "08:00", "17:00", 1000), rule("Evening", "16:00", "22:00", 3000, days=list(range(7))),
        rule("Night", "23:00", "02:00", 5000, days=[3])])
    assert manager.effective_speed_limit(at("16:30"))[0] == 1000            # first match wins
    assert manager.effective_speed_limit(at("19:00"))[0] == 3000
    sat = dt.datetime(2026, 11, 21, 9, 0)
    assert manager.effective_speed_limit(sat) == (0, False)                   # weekday rule, Saturday
    assert manager.effective_speed_limit(at("23:30"))[0] == 5000              # Thursday night
    assert manager.effective_speed_limit(dt.datetime(2026, 11, 20, 1, 0))[0] == 5000   # ...after midnight
    assert manager.effective_speed_limit(dt.datetime(2026, 11, 21, 1, 0)) == (0, False)  # Friday night: no


def test_bad_rules_are_dropped(manager):
    manager.update_settings(speed_rules=[rule("ok", "08:00", "09:00", 1), {"start": "25:00", "end": "x"}, "junk"])
    assert [r["name"] for r in manager.config.settings.speed_rules] == ["ok"]
    manager.update_settings(speed_rules="not a list")
    assert len(manager.config.settings.speed_rules) == 1


def test_old_single_rule_settings_are_migrated(tmp_path):
    import json
    from hypeget.config import Config
    (tmp_path / "settings.json").write_text(json.dumps({
        "speed_rule_enabled": True, "speed_rule_start": "07:30", "speed_rule_end": "18:00", "speed_rule_limit": 2048}))
    rules = Config(str(tmp_path)).settings.speed_rules
    assert rules == [{"name": "Working hours", "enabled": True, "days": [0, 1, 2, 3, 4, 5, 6],
                      "start": "07:30", "end": "18:00", "limit": 2048}]


# ---------------------------------------------------------------- when all downloads finish
def test_shutdown_after_a_60s_countdown_then_resets(manager, server):
    ran = []
    manager.power = ran.append
    manager.set_when_done("shutdown")
    dl = manager.add(server + "/file.bin")
    wait_for(dl)
    t0 = time.time()
    manager._check_when_done(t0)
    manager._check_when_done(t0 + 1)
    assert manager.pending_action["action"] == "shutdown"
    assert 58 <= manager.snapshot()["pending_action"]["in"] <= 60
    manager._check_when_done(t0 + 30)
    assert ran == []                                   # still counting down
    manager._check_when_done(t0 + 61)
    assert ran == ["shutdown"]
    assert manager.config.settings.when_done == "nothing"   # once only
    manager._check_when_done(t0 + 200)
    assert ran == ["shutdown"]


def test_cancel_stops_the_countdown(manager, server):
    ran = []
    manager.power = ran.append
    manager.set_when_done("sleep")
    wait_for(manager.add(server + "/file.bin"))
    t0 = time.time()
    manager._check_when_done(t0)
    manager._check_when_done(t0 + 1)
    assert manager.pending_action
    manager.cancel_when_done()
    manager._check_when_done(t0 + 120)
    assert ran == [] and manager.pending_action is None and manager.config.settings.when_done == "nothing"


def test_nothing_happens_without_downloads(manager):
    ran = []
    manager.power = ran.append
    manager.set_when_done("shutdown")                  # armed while idle
    t0 = time.time()
    for k in range(5):
        manager._check_when_done(t0 + k * 100)
    assert ran == [] and manager.pending_action is None


def test_new_download_restarts_the_wait(manager, server):
    ran = []
    manager.power = ran.append
    manager.set_when_done("shutdown")
    wait_for(manager.add(server + "/file.bin"))
    t0 = time.time()
    manager._check_when_done(t0)
    manager._check_when_done(t0 + 1)
    assert manager.pending_action
    second = manager.add(server + "/file.bin", start=False)
    manager.resume(second.id)                          # more work arrives during the countdown
    manager._check_when_done(t0 + 2)
    assert manager.pending_action is None
    wait_for(second)
    manager._check_when_done(t0 + 3)
    manager._check_when_done(t0 + 50)
    assert ran == []                                   # a fresh 60 s countdown, not the old one
    manager._check_when_done(t0 + 64)
    assert ran == ["shutdown"]


def test_exit_uses_the_app_hook(manager, server):
    exited = []
    manager.on_exit = lambda: exited.append(True)
    manager.set_when_done("exit")
    wait_for(manager.add(server + "/file.bin"))
    t0 = time.time()
    manager._check_when_done(t0)
    manager._check_when_done(t0 + 61)
    assert exited == [True]
