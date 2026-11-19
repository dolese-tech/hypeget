"""YouTube-style quality list (like IDM's menu), JavaScript runtime and cookies."""
import os

import pytest

yt_dlp = pytest.importorskip("yt_dlp")

from hypeget.engine import sites  # noqa: E402

REAL_YDL = yt_dlp.YoutubeDL      # some tests swap yt-dlp for a fake; format checks use the real one

DUR = 600  # seconds


def v(fid, h, codec, ext, tbr, fps=30, acodec="none"):
    return {"format_id": fid, "height": h, "width": h * 16 // 9, "vcodec": codec, "acodec": acodec,
            "ext": ext, "tbr": tbr, "fps": fps, "protocol": "https", "url": f"https://x/{fid}"}


def a(fid, ext, abr, codec):
    return {"format_id": fid, "vcodec": "none", "acodec": codec, "ext": ext, "abr": abr, "tbr": abr,
            "protocol": "https", "url": f"https://x/{fid}"}


# What YouTube offers a client that can run its player JavaScript (simplified).
YOUTUBE = {
    "title": "BIG BOSS | Ep 52", "duration": DUR, "extractor_key": "Youtube",
    "formats": [
        a("139", "m4a", 48, "mp4a.40.5"), a("140", "m4a", 129, "mp4a.40.2"), a("251", "webm", 135, "opus"),
        v("18", 360, "avc1.42001E", "mp4", 500, acodec="mp4a.40.2"),          # the low-quality fallback
        v("160", 144, "avc1.4d400c", "mp4", 80), v("278", 144, "vp9", "webm", 70),
        v("134", 360, "avc1.4d401e", "mp4", 400), v("243", 360, "vp9", "webm", 350),
        v("136", 720, "avc1.4d401f", "mp4", 1500), v("247", 720, "vp9", "webm", 1300),
        v("298", 720, "avc1.4d4020", "mp4", 2500, fps=60),
        v("137", 1080, "avc1.640028", "mp4", 3000), v("248", 1080, "vp9", "webm", 2600),
        v("271", 1440, "vp9", "webm", 9000), v("400", 1440, "av01.0.12M.08", "mp4", 8000),
        v("313", 2160, "vp9", "webm", 18000), v("401", 2160, "av01.0.12M.08", "mp4", 17000),
    ],
}


def select(spec, info=YOUTUBE):
    """Run yt-dlp's real format selector over our spec, as a download would."""
    ydl = REAL_YDL({"quiet": True})
    chosen = list(ydl.build_format_selector(spec)({"formats": info["formats"], "has_merged_format": True,
                                                   "incomplete_formats": False}))
    assert chosen, spec
    f = chosen[0]
    return [x["format_id"] for x in f.get("requested_formats", [f])]


def test_quality_list_like_idm():
    opts = sites.build_options(YOUTUBE, can_merge=True)
    labels = [o["label"] for o in opts]
    assert labels == ["2160p 4K", "1440p 2K", "1080p Full HD", "720p60 HD", "360p", "144p", "Audio only", "MP3 audio"]
    by = {o["label"]: o for o in opts}
    assert by["2160p 4K"]["container"] == "mkv" and by["2160p 4K"]["detail"] == "MKV · VP9"
    assert by["1080p Full HD"]["container"] == "mp4" and by["1080p Full HD"]["detail"] == "MP4 · H.264"
    assert by["Audio only"]["detail"] == "M4A · 129 kbps"
    # sizes: 1080p H.264 (3000 kbps) + best m4a (129 kbps) for 10 minutes
    assert by["1080p Full HD"]["est_size"] == int(3000 * 1000 / 8 * DUR) + int(129 * 1000 / 8 * DUR)


def test_each_choice_downloads_what_it_says():
    by = {o["label"]: o for o in sites.build_options(YOUTUBE, can_merge=True)}
    assert select(by["1080p Full HD"]["format"]) == ["137", "140"]   # H.264 + AAC -> plays everywhere
    assert select(by["720p60 HD"]["format"]) == ["298", "140"]       # the 60 fps version
    assert select(by["2160p 4K"]["format"])[0] in ("313", "401")      # 4K video (VP9/AV1) + audio
    assert len(select(by["2160p 4K"]["format"])) == 2
    assert select(by["Audio only"]["format"]) == ["140"]


def test_without_ffmpeg_only_ready_made_formats():
    opts = sites.build_options(YOUTUBE, can_merge=False)
    assert [o["label"] for o in opts] == ["360p", "Audio only"]
    assert select(opts[0]["format"]) == ["18"]


def test_fallback_only_explains_missing_hd(monkeypatch):
    """What happened on Windows before Deno was bundled: YouTube sent just the fallback."""
    poor = dict(YOUTUBE, formats=[f for f in YOUTUBE["formats"] if f["format_id"] in ("18", "140")])
    monkeypatch.setattr(sites, "youtube_hd_ready", lambda: False)
    monkeypatch.setattr(sites, "ffmpeg_path", lambda: "ffmpeg")

    class FakeYDL:
        def __init__(self, opts): self.opts = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False): return poor

    monkeypatch.setattr(sites.yt_dlp, "YoutubeDL", FakeYDL)
    info = sites.inspect("https://www.youtube.com/watch?v=x")
    assert [o["label"] for o in info["options"]] == ["360p", "Audio only", "MP3 audio"]
    assert "HD and 4K" in info["note"]


def test_js_runtime_is_passed_to_yt_dlp(monkeypatch):
    monkeypatch.setattr(sites, "js_runtime", lambda: ("deno", "C:/HyperGet/deno.exe"))
    assert sites._base_opts({})["js_runtimes"] == {"deno": {"path": "C:/HyperGet/deno.exe"}}
    monkeypatch.setattr(sites, "js_runtime", lambda: None)
    assert "js_runtimes" not in sites._base_opts({})


def test_bundled_deno_is_found_next_to_the_exe(tmp_path, monkeypatch):
    import sys
    exe = tmp_path / "HyperGet.exe"
    exe.write_bytes(b"")
    (tmp_path / "deno.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert sites.js_runtime() == ("deno", str(tmp_path / "deno.exe"))


def test_browser_cookies_become_a_cookie_file():
    opts = sites._base_opts({"Cookie": "SID=abc; HSID=def", "Referer": "https://www.youtube.com/"},
                            "https://www.youtube.com/watch?v=x")
    path = opts["cookiefile"]
    try:
        lines = open(path).read().splitlines()
        assert lines[0] == "# Netscape HTTP Cookie File"
        assert lines[1].split("\t") == [".youtube.com", "TRUE", "/", "TRUE", "0", "SID", "abc"]
        assert "Cookie" not in opts.get("http_headers", {})
        jar = REAL_YDL({"quiet": True, "cookiefile": path}).cookiejar   # yt-dlp accepts it
        assert {c.name for c in jar} == {"SID", "HSID"}
    finally:
        sites._cleanup(opts)
    assert not os.path.exists(path)


# ---------------------------------------------------------------- subtitles, playlists, MP3
class FakeYDL:
    result = None
    seen = []

    def __init__(self, opts):
        self.opts = opts
        FakeYDL.seen.append(opts)

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, url, download=False):
        if download and self.opts.get("postprocessors") and any(
                p["key"] == "FFmpegExtractAudio" for p in self.opts["postprocessors"]):
            open(self.opts["outtmpl"].replace("%(ext)s", "mp3"), "wb").write(b"ID3")   # what FFmpeg leaves
        return FakeYDL.result


def test_subtitle_choices():
    info = {"subtitles": {"sw": [{"ext": "vtt", "name": "Swahili"}], "live_chat": [{}]},
            "automatic_captions": {"en-orig": [{"name": "English (Original)"}], "en": [{"name": "English"}],
                                   "fr": [{"name": "French"}]}}
    assert sites.subtitle_choices(info) == [
        {"id": "sw", "label": "Swahili"},
        {"id": "auto:en-orig", "label": "English (Original) (automatic)"}]


def test_playlist_lists_its_videos(monkeypatch):
    FakeYDL.result = {"_type": "playlist", "title": "Lectures", "entries": [
        {"url": "abc123", "ie_key": "Youtube", "title": "Lecture 1", "duration": 600},
        {"url": "https://www.youtube.com/watch?v=def456", "title": "Lecture 2"}, None]}
    FakeYDL.seen = []
    monkeypatch.setattr(sites.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(sites, "ffmpeg_path", lambda: "ffmpeg")
    info = sites.inspect("https://www.youtube.com/playlist?list=PL1")
    assert FakeYDL.seen[0]["extract_flat"] == "in_playlist"          # fast: no per-video loading
    assert info["kind"] == "playlist" and info["title"] == "Lectures"
    assert [e["url"] for e in info["entries"]] == ["https://www.youtube.com/watch?v=abc123",
                                                   "https://www.youtube.com/watch?v=def456"]
    labels = [o["label"] for o in info["options"]]
    assert labels[:3] == ["Up to 2160p 4K", "Up to 1080p Full HD", "Up to 720p HD"]
    assert labels[-2:] == ["Audio only", "MP3 audio"]
    by = {o["label"]: o for o in info["options"]}
    # the playlist choice works on a real video too: best <=1080p, H.264 + AAC
    assert select(by["Up to 1080p Full HD"]["format"]) == ["137", "140"]
    assert select(by["Up to 2160p 4K"]["format"])[0] in ("313", "401")


def run_capture(monkeypatch, tmp_path, options, quality, title="Song"):
    """Run run_site with a fake yt-dlp and return the options it was given."""
    from hypeget.engine.download import Download
    from hypeget.engine.segments import RunContext
    from hypeget.engine.throttle import Throttle
    import threading
    FakeYDL.seen = []
    FakeYDL.result = {"requested_downloads": [{"filepath": str(tmp_path / "x.webm")}]}
    monkeypatch.setattr(sites.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(sites, "ffmpeg_path", lambda: "ffmpeg")
    dl = Download(url="https://youtu.be/x", save_dir=str(tmp_path), kind="site", title=title,
                  quality=quality, options=options)
    sites.run_site(dl, RunContext(Throttle(0), threading.Event()))
    return FakeYDL.seen[-1], dl


def test_mp3_converts_with_ffmpeg(monkeypatch, tmp_path):
    opts, dl = run_capture(monkeypatch, tmp_path, {"format": "ba/b", "container": "mp3"}, "audio")
    assert {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"} in opts["postprocessors"]
    assert "merge_output_format" not in opts
    assert dl.filename == "Song.mp3"


def test_subtitles_saved_as_srt(monkeypatch, tmp_path):
    opts, _ = run_capture(monkeypatch, tmp_path, {"format": "b", "container": "mp4", "subtitles": "sw"}, "1080p")
    assert opts["writesubtitles"] and opts["subtitleslangs"] == ["sw"]
    assert {"key": "FFmpegSubtitlesConvertor", "format": "srt"} in opts["postprocessors"]
    opts, _ = run_capture(monkeypatch, tmp_path, {"format": "b", "container": "mp4", "subtitles": "auto:en-orig"}, "1080p")
    assert opts["writeautomaticsub"] and opts["subtitleslangs"] == ["en-orig"]
    assert opts["merge_output_format"] == "mp4"
