"""Pro: statistics, file map, data cap, playlist groups."""
import datetime as dt
import time

from conftest import FILE, wait_for

from hypeget.engine.download import Download
from hypeget.engine.stats import Stats


def test_stats_count_traffic_by_day_site_type_and_hour(tmp_path):
    s = Stats(str(tmp_path))
    thu = dt.datetime(2026, 11, 19, 21, 15)
    s.add_traffic(3_000_000, "youtube.com", "Video", thu)
    s.add_traffic(1_000_000, "dolese.tech", "Documents", thu)
    s.add_traffic(2_000_000, "youtube.com", "Video", thu - dt.timedelta(days=1))
    s.add_active_time(2.0, thu)
    s.add_file(now=thu)
    s.add_file(failed=True, now=thu)
    s.save()
    s = Stats(str(tmp_path))                                   # survives a restart
    w = s.summary("week", thu)
    assert w["bytes"] == 6_000_000 and w["files"] == 1 and w["failed"] == 1
    assert [b["label"] for b in w["bars"]][-2:] == ["Wed", "Thu"]
    assert [b["bytes"] for b in w["bars"]][-2:] == [2_000_000, 4_000_000]
    assert w["hosts"][0] == ["youtube.com", 5_000_000] or w["hosts"][0] == ("youtube.com", 5_000_000)
    assert w["hours"][21] == 6_000_000 / 2.0                 # bytes per active second at 21:00
    assert s.today(thu) == {"bytes": 4_000_000, "files": 1, "avg_speed": 2_000_000}
    assert s.month_bytes(thu) == 6_000_000
    y = s.summary("year", thu)
    assert len(y["bars"]) == 12 and y["bars"][-1] == {"label": "Nov", "bytes": 6_000_000}
    assert len(s.summary("month", thu)["bars"]) == 30


def test_change_against_the_previous_period(tmp_path):
    s = Stats(str(tmp_path))
    now = dt.datetime(2026, 11, 19, 12)
    s.add_traffic(100, "a", "Video", now - dt.timedelta(days=8))
    s.add_traffic(150, "a", "Video", now)
    assert s.summary("week", now)["change"] == 0.5


def test_a_real_download_is_counted(manager, server):
    dl = manager.add(server + "/file.bin")
    wait_for(dl, ("complete",))
    time.sleep(1.2)                                            # one more tick
    st = manager.stats.summary("week")
    assert st["bytes"] == len(FILE) and st["files"] == 1
    assert manager.snapshot()["today"]["bytes"] == len(FILE)


def test_file_map():
    d = Download(url="https://x/a.bin", save_dir="/tmp", size=1000, status="downloading")
    d.segments = [[0, 499, 500], [500, 999, 600]]               # first half done, second at 600
    m = d.file_map(10)
    assert m[:5] == [2] * 5 and m[5] == 2 and m[6] == 1 and m[7:] == [0, 0, 0]
    d.status = "complete"
    assert d.file_map(10) == [2] * 10
    h = Download(url="https://x/a.m3u8", save_dir="/tmp", kind="hls", parts_total=4, parts_done=2, status="downloading")
    assert h.file_map(8) == [2, 2, 2, 2, 1, 0, 0, 0]
    assert Download(url="https://x/a", save_dir="/tmp").file_map() is None     # size unknown


def test_data_cap_pauses_once_a_month(manager, server):
    manager.update_settings(data_cap_gb=1, data_cap_action="pause")
    manager.stats.add_traffic(2 * 1024 ** 3, "x", "Video")
    dl = manager.add(server + "/file.bin", start=False)
    manager.resume(dl.id)
    manager._check_data_cap()
    assert manager.snapshot()["cap_reached"] and manager.snapshot()["data_cap"]["hit"]
    wait_for(dl, ("paused",))
    assert not manager.queue_running
    manager.resume(dl.id)                                      # the user decides to carry on
    manager._check_data_cap()
    wait_for(dl, ("complete",))
    manager.update_settings(data_cap_gb=0)
    manager._check_data_cap()
    assert manager.snapshot()["data_cap"] is None and not manager.snapshot()["cap_reached"]


def test_playlist_group_and_thumbnail(manager, server):
    dl = manager.add(server + "/file.bin", group="Physics lectures", thumbnail="https://i.ytimg.com/a.jpg", start=False)
    v = dl.to_view()
    assert v["group"] == "Physics lectures" and v["thumbnail"] == "https://i.ytimg.com/a.jpg"
    bad = manager.add(server + "/file.bin", thumbnail="javascript:alert(1)", start=False)
    assert bad.thumbnail == ""
