import os

from conftest import AUDIO, MASTER, SEGS, wait_for

from hypeget.engine import hls


def test_parse_master():
    m = hls.parse_master(MASTER, "http://h/x/master.m3u8")
    assert [v.label for v in m.variants] == ["1080p", "720p", "360p"]
    assert m.variants[0].uri == "http://h/x/v1080.m3u8"
    assert m.audio[0].uri == "http://h/x/audio.m3u8" and m.audio[0].default


def test_parse_media_key_and_byterange():
    text = """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="k.bin",IV=0x000102030405060708090a0b0c0d0e0f
#EXT-X-MAP:URI="init.mp4"
#EXTINF:2.0,
#EXT-X-BYTERANGE:100@0
seg.mp4
#EXTINF:2.0,
#EXT-X-BYTERANGE:50
seg.mp4
#EXT-X-ENDLIST"""
    pl = hls.parse_media(text, "http://h/a/p.m3u8")
    assert pl.endlist and pl.init.uri == "http://h/a/init.mp4"
    assert pl.segments[0].byterange == (0, 99) and pl.segments[1].byterange == (100, 149)
    assert pl.segments[0].key.iv == bytes(range(16))
    assert pl.duration == 4.0


def test_inspect_master(server):
    info = hls.inspect(server + "/hls/master.m3u8")
    labels = [o["label"] for o in info["options"]]
    assert labels == ["1080p", "720p", "360p"]
    assert info["options"][0]["est_size"] == int(5_000_000 * 24 / 8)
    assert info["options"][0]["audio_url"].endswith("audio.m3u8")


def test_download_chosen_quality(manager, server):
    dl = manager.add(server + "/hls/master.m3u8", quality="720p")
    assert dl.kind == "hls"
    wait_for(dl)
    assert dl.status == "complete", dl.error
    assert dl.filename == "master_720p.ts"
    assert open(dl.target_path, "rb").read() == b"".join(SEGS)
    # no ffmpeg in tests -> audio kept alongside
    stem = os.path.splitext(dl.target_path)[0]
    assert open(stem + ".audio.ts", "rb").read() == b"".join(AUDIO)
    assert dl.parts_done == dl.parts_total == 12
    assert not os.path.exists(dl.target_path + ".parts")
    assert os.path.basename(dl.save_dir) == "Video"


def test_aes128(manager, server):
    dl = manager.add(server + "/hls/enc.m3u8")
    wait_for(dl)
    assert dl.status == "complete", dl.error
    assert open(dl.target_path, "rb").read() == b"".join(SEGS)


def test_hls_detected_by_content_type(manager, server):
    dl = manager.add(server + "/playlist")
    assert dl.kind == "http"
    wait_for(dl)
    assert dl.status == "complete", dl.error
    assert dl.kind == "hls"


def test_live_and_drm_refused(manager, server):
    live = manager.add(server + "/hls/live.m3u8")
    drm = manager.add(server + "/hls/drm.m3u8")
    wait_for(live)
    wait_for(drm)
    assert live.status == "error" and "Live" in live.error
    assert drm.status == "error" and "DRM" in drm.error


def test_hls_remux_with_ffmpeg(manager, server, monkeypatch):
    """With ffmpeg present the output is .mp4 (our random bytes can't be remuxed,
    so it falls back to .ts without losing data)."""
    import shutil
    if not shutil.which("ffmpeg"):
        return
    monkeypatch.setattr("hypeget.engine.hls.ffmpeg_path", lambda: shutil.which("ffmpeg"))
    dl = manager.add(server + "/hls/v360.m3u8")
    wait_for(dl)
    assert dl.status == "complete", dl.error
    assert open(dl.target_path, "rb").read() == b"".join(SEGS)
