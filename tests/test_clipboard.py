"""Clipboard watching: copied download links are offered once, others ignored."""
from hypeget.clipboard import ClipboardWatcher, downloadable_link


def test_which_links_are_offered():
    assert downloadable_link("https://example.com/setup.exe") == "https://example.com/setup.exe"
    assert downloadable_link("  https://cdn.x.org/a/movie.MP4?token=1 \n") == "https://cdn.x.org/a/movie.MP4?token=1"
    assert downloadable_link("https://x.org/live/master.m3u8")
    assert downloadable_link("https://example.com/about") is None          # an ordinary page
    assert downloadable_link("see https://example.com/a.zip") is None       # not just a link
    assert downloadable_link("ftp://example.com/a.zip") is None
    assert downloadable_link("") is None and downloadable_link(None) is None
    yt = "https://www.youtube.com/watch?v=abc"
    assert downloadable_link(yt) is None
    assert downloadable_link(yt, supports_site=lambda u: "youtube.com" in u) == yt


def make(clip, known=(), enabled=True):
    offered = []
    w = ClipboardWatcher(on_link=offered.append, is_known=lambda u: u in known,
                         enabled=lambda: enabled, read=lambda: clip["text"])
    return w, offered


def test_offers_a_new_copy_once():
    clip = {"text": "https://example.com/old.zip"}
    w, offered = make(clip)
    w.prime()                                   # what was there at startup is not offered
    assert w.poll() is None
    clip["text"] = "https://example.com/new.zip"
    assert w.poll() == "https://example.com/new.zip"
    assert w.poll() is None                     # same text again: once only
    assert offered == ["https://example.com/new.zip"]


def test_skips_known_links_and_respects_the_setting():
    clip = {"text": ""}
    w, offered = make(clip, known={"https://example.com/have.zip"})
    w.prime()
    clip["text"] = "https://example.com/have.zip"
    assert w.poll() is None
    w2, offered2 = make(clip, enabled=False)
    w2.prime()
    clip["text"] = "https://example.com/other.zip"
    assert w2.poll() is None and offered2 == []


def test_read_errors_are_ignored():
    def boom():
        raise OSError("clipboard busy")
    w = ClipboardWatcher(on_link=lambda u: None, is_known=lambda u: False, enabled=lambda: True, read=boom)
    w.prime()
    assert w.poll() is None
