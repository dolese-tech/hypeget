// HyperGet extension service worker.
// - Detects media (HLS playlists, video/audio files) loaded by each tab.
// - Talks to the HyperGet app on 127.0.0.1 (inspect qualities, add downloads).
// - Optional: hands browser downloads over to HyperGet (like IDM).

importScripts("config.js");

const DEFAULTS = { port: 52817, intercept: true, minInterceptMB: 1 };
const media = new Map();          // tabId -> Map(url -> item)
const reqHeaders = new Map();     // requestId -> {referer, cookie}

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}

async function app(path, body) {
  const { port } = await settings();
  const res = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: body ? "POST" : "GET",
    headers: { "X-HyperGet": "1", "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HyperGet error ${res.status}`);
  return data;
}

async function appAlive() {
  try { await app("/api/ping"); return true; } catch { return false; }
}

// ------------------------------------------------------------------ detection
const SEGMENT = /\.(ts|m4s|aac|vtt|webvtt|key)(\?|$)/i;
const IGNORE_HOSTS = /(^|\.)(googlevideo\.com|doubleclick\.net|googlesyndication\.com)$/i;
const HLS_TYPES = /mpegurl/i;

function classify(url, type, size) {
  if (SEGMENT.test(url)) return null;
  const path = url.split("?")[0].toLowerCase();
  if (HLS_TYPES.test(type) || path.endsWith(".m3u8")) return "hls";
  if (/^(video|audio)\//i.test(type) || /\.(mp4|webm|mkv|mov|m4v|mp3|m4a|flac|ogg|opus)$/.test(path)) {
    if (size && size < 300 * 1024) return null;          // ads, previews, beeps
    return "file";
  }
  return null;
}

chrome.webRequest.onBeforeSendHeaders.addListener((d) => {
  const h = {};
  for (const x of d.requestHeaders || []) {
    const n = x.name.toLowerCase();
    if (n === "referer" || n === "cookie") h[n] = x.value;
  }
  if (h.referer || h.cookie) reqHeaders.set(d.requestId, h);
}, { urls: ["<all_urls>"], types: ["xmlhttprequest", "media", "other", "object"] },
["requestHeaders", "extraHeaders"]);

chrome.webRequest.onHeadersReceived.addListener((d) => {
  const sent = reqHeaders.get(d.requestId) || {};
  reqHeaders.delete(d.requestId);
  if (d.tabId < 0 || d.statusCode >= 400) return;
  let host = "";
  try { host = new URL(d.url).hostname; } catch { return; }
  if (IGNORE_HOSTS.test(host)) return;
  const get = (n) => d.responseHeaders?.find((x) => x.name.toLowerCase() === n)?.value || "";
  const type = get("content-type");
  const range = get("content-range").match(/\/(\d+)$/);
  const size = range ? +range[1] : +get("content-length") || 0;
  const kind = classify(d.url, type, size);
  if (!kind) return;
  let list = media.get(d.tabId);
  if (!list) media.set(d.tabId, (list = new Map()));
  if (list.has(d.url)) return;
  // HLS: a variant playlist after a master is just one of its qualities; keep the master.
  list.set(d.url, {
    url: d.url, kind, type, size, time: Date.now(),
    headers: { Referer: sent.referer || "", Cookie: sent.cookie || "" },
    name: decodeURIComponent(d.url.split("?")[0].split("/").pop() || "media"),
  });
  updateBadge(d.tabId);
}, { urls: ["<all_urls>"], types: ["xmlhttprequest", "media", "other", "object"] }, ["responseHeaders"]);

chrome.webRequest.onErrorOccurred.addListener((d) => reqHeaders.delete(d.requestId), { urls: ["<all_urls>"] });

function updateBadge(tabId) {
  const n = media.get(tabId)?.size || 0;
  chrome.action.setBadgeText({ tabId, text: n ? String(n) : "" });
  chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" });
}

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "loading" && info.url) { media.delete(tabId); updateBadge(tabId); }
});
chrome.tabs.onRemoved.addListener((tabId) => media.delete(tabId));

function tabMedia(tabId) {
  return [...(media.get(tabId)?.values() || [])].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "hls" ? -1 : 1;
    return (b.size || 0) - (a.size || 0);
  });
}

// ------------------------------------------------------------------ inspect / download
async function cleanHeaders(h, url) {
  const out = {};
  if (h?.Referer) out.Referer = h.Referer;
  if (h?.Cookie) out.Cookie = h.Cookie;
  if (!out.Cookie && url) {
    try {
      const cookies = await chrome.cookies.getAll({ url });
      if (cookies.length) out.Cookie = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    } catch { /* no access */ }
  }
  return out;
}

// Pick what the page's video really is: a supported site page (YouTube...) or the
// best media the tab loaded (HLS master first, then the biggest file).
async function videoOptions(tabId, pageUrl, src, pageTitle) {
  if (hypergetRestricted(pageUrl)) {
    return { ok: false, error: "Video download isn't available on this site from the browser. Copy the page link and paste it into HyperGet (Add URL)." };
  }
  const tried = [];
  const candidates = [];
  if (src && /^https?:/.test(src)) candidates.push({ url: src, headers: { Referer: pageUrl } });
  candidates.push({ url: pageUrl, headers: { Referer: pageUrl }, page: true });
  for (const m of tabMedia(tabId)) candidates.push(m);
  let lastErr = null;
  for (const c of candidates) {
    if (tried.includes(c.url)) continue;
    tried.push(c.url);
    try {
      const headers = await cleanHeaders(c.headers, c.url);
      const info = await app("/api/inspect", { url: c.url, headers });
      if (c.page && info.kind === "http") continue;   // page itself isn't a video
      if (info.kind === "hls" && pageTitle) info.title = pageTitle;   // "master" -> real title
      return { ok: true, info, source: { url: c.url, headers, page_url: pageUrl } };
    } catch (e) {
      lastErr = e;
    }
  }
  return { ok: false, error: lastErr ? lastErr.message : "No downloadable video found on this page yet. Start playing it, then try again." };
}

async function sendDownload(source, info, option) {
  return app("/api/downloads", {
    url: source.url, kind: info.kind, headers: source.headers, page_url: source.page_url || "",
    title: info.kind === "http" ? "" : info.title, quality: option.quality || "",
    options: { variant_url: option.variant_url, audio_url: option.audio_url, format: option.format },
  });
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    const tabId = msg.tabId ?? sender.tab?.id;
    switch (msg.type) {
      case "status": return { alive: await appAlive(), settings: await settings() };
      case "media": return { items: tabMedia(tabId) };
      case "videoOptions": return videoOptions(tabId, msg.pageUrl, msg.src, msg.pageTitle);
      case "inspect": {
        const headers = await cleanHeaders(msg.headers, msg.url);
        const info = await app("/api/inspect", { url: msg.url, headers });
        return { ok: true, info, source: { url: msg.url, headers, page_url: msg.pageUrl || "" } };
      }
      case "download": await sendDownload(msg.source, msg.info, msg.option); return { ok: true };
      case "saveSettings": await chrome.storage.local.set(msg.settings); return { ok: true };
      default: return { ok: false, error: "unknown message" };
    }
  })().then(reply, (e) => reply({ ok: false, error: e.message }));
  return true;
});

// ------------------------------------------------------------------ context menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "hg-link", title: "Download with HyperGet", contexts: ["link", "video", "audio", "image"] });
  chrome.contextMenus.create({ id: "hg-page", title: "Download video on this page with HyperGet", contexts: ["page"] });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === "hg-link") {
      const url = info.linkUrl || info.srcUrl;
      if (!url || !/^https?:/.test(url)) return;
      const headers = await cleanHeaders({ Referer: info.pageUrl }, url);
      await app("/api/downloads", { url, headers, page_url: info.pageUrl });
    } else if (info.menuItemId === "hg-page" && tab?.id != null) {
      chrome.tabs.sendMessage(tab.id, { type: "openPicker" });
    }
  } catch (e) {
    console.warn("HyperGet:", e.message);
  }
});

// ------------------------------------------------------------------ take over browser downloads
chrome.downloads.onCreated.addListener(async (item) => {
  const s = await settings();
  if (!s.intercept || !/^https?:/.test(item.finalUrl || item.url)) return;
  if (item.byExtensionId === chrome.runtime.id) return;
  const size = item.totalBytes || item.fileSize || 0;
  if (size && size < s.minInterceptMB * 1024 * 1024) return;
  if (!(await appAlive())) return;            // app not running: let the browser handle it
  const url = item.finalUrl || item.url;
  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
    const headers = await cleanHeaders({ Referer: item.referrer || "" }, url);
    const name = item.filename ? item.filename.split(/[\\/]/).pop() : "";
    await app("/api/downloads", { url, headers, page_url: item.referrer || "", ...(name ? { filename: name } : {}) });
  } catch (e) {
    console.warn("HyperGet: could not take over download, retrying in browser", e);
    chrome.downloads.download({ url });
  }
});
