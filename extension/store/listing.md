# Store listing: HyperGet Integration

Copy-paste text for the Chrome Web Store and Microsoft Edge Add-ons. Upload
`dist/extension/hyperget-extension-<version>-store.zip` (made by
`python tools/build_extension.py`), never the `-full` zip.

---

## Basics (both stores)

| Field | Value |
|---|---|
| Name | HyperGet Integration (comes from the package) |
| Summary / short description | Send downloads and videos to the HyperGet download manager, with a Download button on videos and a quality picker. |
| Category | Chrome: **Productivity → Tools** · Edge: **Productivity** |
| Language | English |
| Website / homepage | https://hyperget.dolese.tech |
| Support email | support@dolese.tech |
| Support URL | https://hyperget.dolese.tech/#faq |
| Privacy policy URL | https://hyperget.dolese.tech/privacy |
| Visibility | Public |
| Price | Free (the extension itself) |

## Detailed description

> Paste everything between the lines.

---
HyperGet Integration connects your browser to HyperGet, the download manager for Windows from dolese Tech.

HyperGet splits every file across up to eight connections, resumes after a dropped connection or a restart, and saves streaming video in the quality you choose. This extension brings that into your browser.

WHAT IT DOES
• Download button on videos: hover a video player and click "Download this video". Pick 1080p, 720p or another quality, with the size shown before you start.
• See what each tab is playing: the toolbar button lists the video streams and media files the current page has loaded.
• Hands downloads to HyperGet: normal browser downloads larger than 1 MB go to HyperGet, so they get eight connections and resume. You choose the size limit, or switch this off.
• Right-click any link, image, audio or video and choose "Download with HyperGet".
• Signed-in downloads keep working: the referrer and cookies for the file you download are passed to the app.

REQUIREMENTS
The HyperGet app for Windows 10 or 11 must be installed. Get it at https://hyperget.dolese.tech/download. If HyperGet is closed, the extension starts it; if it isn't installed, the browser downloads files as usual.

PRIVACY
The extension talks only to the HyperGet app on your own computer, through the browser's native messaging. It sends nothing to dolese Tech or anyone else, has no analytics and needs no account. Details: https://hyperget.dolese.tech/privacy

Some sites don't allow downloading their videos from the browser; on those the Download button isn't shown. DRM-protected streams (for example Netflix or Spotify) are not supported. Download only content you have the right to save.
---

## Images (in this folder)

| Store slot | File | Size |
|---|---|---|
| Chrome store icon | `store-icon-128.png` | 128×128 (96 px artwork + transparent padding) |
| Edge logo | `edge-logo-300.png` | 300×300 |
| Screenshots (both stores, in this order) | `screenshot-1-video-button.png`, `screenshot-2-detected-media.png`, `screenshot-3-app.png`, `screenshot-4-private.png` | 1280×800 |
| Small promo tile (both) | `promo-small-440x280.png` | 440×280 |
| Marquee (Chrome) / large promo tile (Edge) | `promo-marquee-1400x560.png` | 1400×560 |

---

## Chrome Web Store: Privacy practices tab

**Single purpose**

> Sends downloads and videos from the browser to the HyperGet download manager app installed on the user's computer.

**Permission justifications**

| Permission | Justification to paste |
|---|---|
| `webRequest` | Detects video streams (HLS playlists) and media files that the open tab loads, so the extension can list them and offer to download them, and reads the referrer/cookie headers of those requests so signed-in downloads work in the app. |
| `downloads` | Optional take-over of browser downloads: when the user enables it and the HyperGet app is running, a new browser download is cancelled and handed to HyperGet instead. |
| `cookies` | Reads the cookies for the single file the user chooses to download, so that downloads which require the user to be signed in work in the HyperGet app. |
| `contextMenus` | Adds "Download with HyperGet" to the right-click menu for links, images, audio and video. |
| `storage` | Saves the user's two settings: take over downloads on/off and the minimum file size. |
| `nativeMessaging` | Connects to the HyperGet desktop app installed on the user's computer (native host `com.dolese.hyperget`), which performs the downloads. This is the extension's only way to reach the app. |
| Host permission `<all_urls>` | Needed on every site because the user can download from any site: to detect media in any tab, show the Download button on any video, and read cookies for the chosen file's site. |
| Content script on all sites | Shows the "Download this video" button and quality menu over video players. It does not read or change page content otherwise. |

**Remote code:** No, I am not using remote code. (All JavaScript ships in the package.)

**Data usage:** tick these, as the extension handles them locally to do its job:

- **Web history**: URLs of media requests and the page address of a download.
- **Authentication information**: cookies of the file being downloaded.

Then tick all three certifications:

- I do not sell or transfer user data to third parties, outside of the approved use cases.
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose.
- I do not use or transfer user data to determine creditworthiness or for lending purposes.

> The data never leaves the computer: it goes only to the HyperGet app through native messaging. Declaring it anyway is the safe choice in review.

---

## Edge Add-ons: extra fields

**Search terms** (up to 7): download manager, video downloader, HLS, resume downloads, download accelerator, HyperGet, m3u8

**Notes for certification** (paste):

> This extension works with the HyperGet desktop app for Windows (https://hyperget.dolese.tech/download). To test:
> 1. Install and start HyperGet.
> 2. Open any page with an HTML5 video, hover the video and click "Download this video", then pick a quality: the download appears in HyperGet.
> 3. Click the toolbar button to see media detected on the tab.
> If HyperGet is closed, the extension starts it. Without HyperGet installed, the popup shows "Not installed" and the browser keeps downloading files normally. The extension communicates only with the HyperGet app through native messaging (host `com.dolese.hyperget`); it makes no network requests of its own.

Use the same notes in the Chrome Web Store if a reviewer asks for test instructions.
