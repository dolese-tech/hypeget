# HyperGet Downloader

A multi-connection download manager with HLS stream support, a quality picker for
videos, and a browser extension. The UI is built to match `docs/mockup/main_window.png`.

## Features

- **Fast downloads**: splits files into up to 8 (configurable, max 32) parallel connections and
  re-splits the largest remaining range when a connection finishes.
- **Pause / resume**, including after closing the app, when the server supports byte ranges.
  Servers that don't still work (single stream, restarts from zero).
- **HLS (`.m3u8`)**: picks a quality from master playlists, downloads segments in parallel,
  handles separate audio tracks, fMP4, byte-range segments and standard AES-128 encryption.
  With FFmpeg installed the result is merged into one `.mp4`; without it you get a `.ts`.
  DRM-protected and live streams are refused.
- **Video sites (optional)**: with `yt-dlp` installed, pasting a YouTube (or other supported site)
  link shows the available qualities (1080p, 720p, … , audio only).
- **Queue & scheduler**: limit how many run at once; start/stop the queue at set times each day.
- **Speed limit** shared by all downloads.
- **Grabber**: scan a web page and pick which linked files to download.
- **Auto-filing** into `Downloads/Compressed`, `Documents`, `Music`, `Programs`, `Video`.
- **Browser extension** (Chrome / Edge): a *Download this video* button over players with a
  quality menu, a list of media detected on the tab, right-click *Download with HyperGet*, and
  optional take-over of normal browser downloads.
- Light and dark theme.

## Download (Windows)

Every push builds Windows downloads with GitHub Actions (**Actions → Windows build → Artifacts**):

- `HyperGet-Setup-<version>.exe`: installer (Start menu + desktop shortcut, uninstaller)
- `HyperGet-portable-<version>.zip`: unzip and run `HyperGet.exe`

Both include FFmpeg, yt-dlp and the `extension` folder. Push a tag such as `v0.1.0` to publish
them on the Releases page. Windows needs the Microsoft Edge WebView2 runtime (already present
on Windows 10/11). The build isn't code-signed yet, so SmartScreen will warn on first run:
choose *More info → Run anyway*.

## Website

`website/` is the product site (one static page plus screenshots in `website/assets/`).
It is published to GitHub Pages by `.github/workflows/website.yml` when changes reach the
main branch. Turn it on once under **Settings → Pages → Source: GitHub Actions**. To preview
locally: `cd website && python -m http.server`.

## Run from source

```bash
pip install -e .              # pywebview + cryptography
pip install yt-dlp            # optional: YouTube & other video sites
# optional: install FFmpeg and put it on PATH to merge HLS audio+video into MP4

python -m hypeget             # native window
python -m hypeget --browser   # or open the UI in your web browser
```

Settings and the download list live in `~/.hypeget` (override with `HYPEGET_HOME`).

## Browser extension

1. Open `chrome://extensions` (or `edge://extensions`) and turn on **Developer mode**.
2. **Load unpacked**, then choose the `extension/` folder.
3. Keep HyperGet running. Hover a video and click **Download this video**, then pick a quality.

The extension talks to the app at `http://127.0.0.1:52817`. That API only listens on
loopback, checks the `Host` header, requires an `X-HyperGet` header and only accepts
cross-origin calls from browser extensions, so ordinary websites cannot drive it.

> Only download content you have the right to save. Many video sites' terms restrict
> downloading. DRM-protected services (Netflix, Spotify, …) are not supported.

## Layout

```
hypeget/
  app.py            window + startup         server.py   local API (UI + extension)
  config.py         settings                 storage/    persisted download list
  engine/
    manager.py      queue, start/pause/resume, speed, persistence
    segments.py     multi-connection HTTP     hls.py      HLS playlists & segments
    sites.py        yt-dlp integration        media.py    "what qualities does this link have?"
    net.py          HTTP helpers / probe      grabber.py  page link scanner
    throttle.py     speed limit               scheduler.py daily start/stop
  ui/               HTML/CSS/JS (bundled Inter font, no build step)
extension/          Chrome/Edge MV3 extension
tests/              pytest engine/API tests, Playwright UI + extension scripts
```

## Tests

```bash
pip install pytest && python -m pytest
# UI screenshot vs mockup data (needs Playwright + a running app on port 52817):
node tests/ui/screenshot.mjs http://127.0.0.1:52817/ shot.png
# Extension end-to-end (needs the test file server; see tests/conftest.py):
node tests/ui/extension_e2e.mjs <page-url> <app-port> ext.png
```
