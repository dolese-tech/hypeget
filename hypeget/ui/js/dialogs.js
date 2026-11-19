import { api } from "./api.js";
import { bytes, esc, isUrl } from "./format.js";

export function toast(text, ms = 2600) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

export function modal({ title, body, buttons = [], wide = false, left = "", size = "" }) {
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `
    <div class="dialog ${wide ? "wide" : ""} ${size}" role="dialog" aria-modal="true">
      <header><h2>${esc(title)}</h2><button class="x" aria-label="Close">×</button></header>
      <div class="content">${body}</div>
      <footer><span class="left">${left}</span>${buttons.map((b, i) =>
        `<button class="${b.cls || "btn"}" data-i="${i}">${esc(b.label)}</button>`).join("")}</footer>
    </div>`;
  const close = () => { ov.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") {
      const primary = buttons.findIndex((b) => b.primary);
      if (primary >= 0) { e.preventDefault(); ov.querySelector(`[data-i="${primary}"]`).click(); }
    }
  };
  document.addEventListener("keydown", onKey, true);
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(); });
  ov.querySelector(".x").onclick = close;
  ov.querySelectorAll("footer [data-i]").forEach((btn) => {
    btn.onclick = async () => {
      const b = buttons[+btn.dataset.i];
      if (!b.onClick) return close();
      btn.disabled = true;
      try {
        if ((await b.onClick(ov)) !== false) close();
      } catch (err) {
        showError(ov, err.message);
      } finally { btn.disabled = false; }
    };
  });
  document.body.appendChild(ov);
  setTimeout(() => ov.querySelector("input:not([type=checkbox]):not([type=radio]), textarea")?.focus(), 30);
  return { el: ov, close };
}

function showError(ov, text) {
  let m = ov.querySelector(".msg.error");
  if (!m) {
    m = document.createElement("div");
    m.className = "msg error";
    ov.querySelector(".content").prepend(m);
  }
  m.textContent = text;
}

// ---------------------------------------------------------------- Add URL (video picker, like the Pro mockup)
function fmtDur(sec) {
  if (!sec) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = String(sec % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

function views(n) {
  if (!n) return "";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B views`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M views`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}K views`;
  return `${n} views`;
}

function qparts(o) {
  // "1080p Full HD" -> ["1080p", "Full HD"]; "Up to 720p HD" -> ["≤ 720p", "HD"]; "Audio only" -> ["Audio", "M4A"]
  let label = o.label.replace(/^Up to /, "≤ ");
  if (o.container === "mp3") return ["MP3", ""];
  if (o.quality === "audio") return ["Audio", (o.container || "").toUpperCase()];
  const m = label.match(/^(≤ )?(\d+p\d*)\s*(.*)$/);
  return m ? [(m[1] || "") + m[2], m[3]] : [label, ""];
}

function folderFor(settings, ...parts) {
  const base = settings?.download_dir || "";
  const sep = base.includes("\\") ? "\\" : "/";
  const clean = parts.map((p) => String(p).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().slice(0, 80)).filter(Boolean);
  return [base.replace(/[\\/]+$/, ""), ...clean].join(sep);
}

export function addUrlDialog(prefill = "", onDone, settings = null) {
  let info = null, chosen = null, seq = 0, tab = "video", when = "now";
  const dlg = modal({
    title: "Add URL",
    size: "xl",
    body: `
      <div class="field"><label>Address</label><input type="url" id="au-url" placeholder="https://example.com/file.zip, a video page, a playlist or a .m3u8 link" value="${esc(prefill)}"></div>
      <div id="au-info"></div>
      <div id="au-more">
        <div class="field" id="au-name-field"><label>Save as</label><input type="text" id="au-name" placeholder="Detected automatically"></div>
        <div class="opts3" style="margin-top:0">
          <div class="field" id="au-sub-field" style="display:none"><label>Subtitles</label><select id="au-sub"><option value="">None</option></select>
            <div class="toggle" id="au-embed-row"><span class="sw on" id="au-embed"></span>Also inside the video</div></div>
          <div class="field"><label>Save to</label><input type="text" id="au-dir" placeholder="Automatic (by category)"></div>
          <div class="field"><label>When</label><div class="seg" id="au-when"><span data-w="now" class="on">Now</span><span data-w="later">Later</span></div>
            <div class="hint">Later: you or the Scheduler start it.</div></div>
        </div>
      </div>`,
    left: `<span id="au-left"></span>`,
    buttons: [
      { label: "Cancel" },
      { label: "Download", cls: "btn-primary", primary: true, onClick: async (ov) => {
        const url = ov.querySelector("#au-url").value.trim();
        if (!isUrl(url)) throw new Error("Enter a valid http(s) link.");
        const start = when === "now";
        const dir = ov.querySelector("#au-dir").value.trim();
        if (info?.kind === "playlist") {
          const picked = [...ov.querySelectorAll(".pl-item input:checked")].map((c) => info.entries[+c.dataset.i]);
          if (!picked.length) throw new Error("Select at least one video.");
          const sub = "";
          await api.addMany(picked.map((e) => ({ url: e.url, kind: "site", title: e.title, start, group: info.title,
            quality: chosen.quality || "", page_url: url, save_dir: dir || undefined,
            options: { format: chosen.format, container: chosen.container, ...(sub && chosen.quality !== "audio" ? { subtitles: sub } : {}) } })));
          toast(`Added ${picked.length} video${picked.length > 1 ? "s" : ""}`);
          onDone?.();
          return;
        }
        const name = ov.querySelector("#au-name").value.trim();
        const item = { url, start };
        if (dir) item.save_dir = dir;
        if (info && chosen) {
          item.kind = info.kind;
          item.title = info.kind === "http" ? "" : info.title;
          item.quality = chosen.quality || "";
          if (info.thumbnail) item.thumbnail = info.thumbnail;
          item.options = { variant_url: chosen.variant_url, audio_url: chosen.audio_url, format: chosen.format, container: chosen.container };
          const sub = ov.querySelector("#au-sub")?.value;
          if (sub && ov.querySelector("#au-sub-field").style.display !== "none" && chosen.container !== "mp3" && chosen.quality !== "audio") {
            item.options.subtitles = sub;
            if (ov.querySelector("#au-embed")?.classList.contains("on")) item.options.embed_subs = true;
          }
        }
        if (name && name !== (info?.suggested || "")) item.filename = name;
        await api.add(item);
        onDone?.();
      } },
    ],
  });
  const ov = dlg.el;
  const urlIn = ov.querySelector("#au-url");
  const box = ov.querySelector("#au-info");
  const nameIn = ov.querySelector("#au-name");
  const dirIn = ov.querySelector("#au-dir");
  const left = ov.querySelector("#au-left");
  const primary = ov.querySelector("footer .btn-primary");
  ov.querySelector("#au-embed-row").onclick = () => ov.querySelector("#au-embed").classList.toggle("on");
  ov.querySelectorAll("#au-when span").forEach((s) => s.onclick = () => {
    when = s.dataset.w;
    ov.querySelectorAll("#au-when span").forEach((x) => x.classList.toggle("on", x === s));
  });

  async function check() {
    const url = urlIn.value.trim();
    info = chosen = null;
    tab = "video";
    if (!isUrl(url)) { box.innerHTML = ""; updateFooter(); return; }
    const my = ++seq;
    box.innerHTML = `<div class="msg info"><span class="spinner"></span>Checking link…</div>`;
    try {
      const res = await api.inspect(url);
      if (my !== seq) return;
      info = res;
      chosen = res.options.find((o) => /1080p/.test(o.label)) || res.options[0];
      if (info.kind === "playlist" && !dirIn.dataset.touched) dirIn.value = folderFor(settings, "Video", info.title);
      renderInfo();
    } catch (e) {
      if (my !== seq) return;
      box.innerHTML = `<div class="msg error">${esc(e.message)} — you can still try to download it.</div>`;
      updateFooter();
    }
  }

  function suggestedName() {
    if (!info) return "";
    if (info.kind === "http") return info.filename;
    const ext = "." + (chosen?.container || (chosen?.quality === "audio" ? "m4a" : "mp4"));
    const q = chosen?.quality && chosen.quality !== "audio" ? `_${chosen.quality}` : "";
    return `${info.title}${q}${ext}`;
  }

  function updateFooter() {
    const size = chosen?.est_size;
    if (info?.kind === "playlist") {
      const n = ov.querySelectorAll(".pl-item input:checked").length;
      primary.textContent = `Download ${n} video${n === 1 ? "" : "s"}`;
      left.textContent = "";
    } else {
      primary.textContent = size ? `Download ${bytes(size)}` : "Download";
      left.textContent = "";
    }
  }

  function cards(opts) {
    const best = opts.find((o) => /1080p/.test(o.label));
    return `<div class="qgrid">${opts.map((o) => {
      const [r, small] = qparts(o);
      const i = info.options.indexOf(o);
      const tag = /2160p|4K/.test(o.label) ? `<span class="tag p">4K</span>` : o === best ? `<span class="tag">BEST FIT</span>` : "";
      return `<div class="qcard ${o === chosen ? "sel" : ""}" data-i="${i}">${tag}<div class="r">${esc(r)}<small>${esc(small)}</small></div>
        <div class="t">${esc(o.detail || "")}</div><div class="sz">${o.est_size ? "≈ " + bytes(o.est_size) : "&nbsp;"}</div></div>`;
    }).join("")}</div>`;
  }

  function renderInfo() {
    const isList = info.kind === "playlist";
    const isSite = info.kind === "site";
    ov.querySelector("#au-name-field").style.display = isList ? "none" : "";
    let html = "";
    if (info.kind === "http") {
      const o = info.options[0];
      html = `<div class="msg info">${esc(info.filename)} · ${o.est_size ? bytes(o.est_size) : "size unknown"} · ${esc(o.detail)}</div>`;
    } else if (isList) {
      html = `<div class="field"><label>Playlist <span style="color:var(--text-3);font-weight:400">— ${esc(info.title)} · ${info.entries.length} videos</span></label>
        <label class="check"><input type="checkbox" id="pl-all" checked> Select all</label>
        <div class="grab-list">${info.entries.map((e, i) => `
          <label class="grab-item pl-item"><input type="checkbox" data-i="${i}" checked>
          <div style="min-width:0"><div class="n">${esc(e.title)}</div><div class="u">${e.duration ? fmtDur(e.duration) + " · " : ""}${esc(e.url)}</div></div></label>`).join("")}</div></div>
        <div class="field"><label>Quality for every video</label>${cards(info.options)}</div>`;
    } else {
      const audio = info.options.filter((o) => o.quality === "audio");
      const video = info.options.filter((o) => o.quality !== "audio");
      if (!video.length) tab = "audio";
      const shown = tab === "audio" ? audio : video;
      if (!shown.includes(chosen)) chosen = shown[0];
      const top = video[0] ? qparts(video[0])[0] : "";
      const meta = [info.uploader, (info.site || "").replace(/^Youtube$/i, "YouTube"), views(info.views)].filter(Boolean).map(esc).join(" · ");
      const tags = [];
      if (top) tags.push(`<span class="chip">Up to ${esc(top)}</span>`);
      if (info.subtitles?.length) tags.push(`<span class="chip g">Subtitles: ${info.subtitles.length} language${info.subtitles.length > 1 ? "s" : ""}</span>`);
      if (audio.some((o) => o.container === "mp3")) tags.push(`<span class="chip q">MP3</span>`);
      const thumb = /^https:\/\//.test(info.thumbnail || "")
        ? info.thumbnail.replace(/[\s"'()\\<>]/g, (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).replace(/&/g, "&amp;") : "";
      const poster = thumb ? `<div class="poster" style="background-image:url(${thumb})">` : `<div class="poster blank">`;
      html = `
        ${info.note ? `<div class="msg info">${esc(info.note)}</div>` : ""}
        <div class="vid">${poster}${info.duration ? `<span class="dur">${fmtDur(info.duration)}</span>` : ""}</div>
          <div><h3>${esc(info.title)}</h3><div class="meta">${meta || "&nbsp;"}</div><div class="tags">${tags.join("")}</div></div></div>
        ${isSite && audio.length && video.length ? `<div class="tabsbar" style="padding:0;margin-bottom:12px"><span data-tab="video" class="${tab === "video" ? "on" : ""}">Video</span><span data-tab="audio" class="${tab === "audio" ? "on" : ""}">Audio</span></div>` : ""}
        <div class="field"><label>Quality</label>${cards(shown)}</div>`;
    }
    const subs = (isList ? [] : info.subtitles || []);
    const subField = ov.querySelector("#au-sub-field"), subSel = ov.querySelector("#au-sub");
    const showSubs = subs.length > 0 && tab === "video";
    subField.style.display = showSubs ? "" : "none";
    const want = `<option value="">None</option>${subs.map((t) => `<option value="${esc(t.id)}">${esc(t.label)}</option>`).join("")}`;
    if (subSel.dataset.h !== want) { subSel.innerHTML = want; subSel.dataset.h = want; }
    box.innerHTML = html;
    const all = box.querySelector("#pl-all");
    if (all) all.onchange = () => { box.querySelectorAll(".pl-item input").forEach((c) => c.checked = all.checked); updateFooter(); };
    box.querySelectorAll(".pl-item input").forEach((c) => c.onchange = updateFooter);
    box.querySelectorAll("[data-tab]").forEach((t) => t.onclick = () => { tab = t.dataset.tab; chosen = null; renderInfo(); });

    box.querySelectorAll(".qcard").forEach((q) => q.onclick = () => {
      chosen = info.options[+q.dataset.i];
      box.querySelectorAll(".qcard").forEach((x) => x.classList.toggle("sel", x === q));
      const s = suggestedName();
      if (!nameIn.dataset.touched) nameIn.value = s;
      info.suggested = s;
      updateFooter();
    });
    info.suggested = suggestedName();
    if (!nameIn.dataset.touched) nameIn.value = info.suggested;
    updateFooter();
  }

  let timer;
  urlIn.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(check, 450); });
  nameIn.addEventListener("input", () => { nameIn.dataset.touched = "1"; });
  dirIn.addEventListener("input", () => { dirIn.dataset.touched = "1"; });
  if (prefill) check();
}

// ---------------------------------------------------------------- Batch
export function batchDialog(onDone) {
  modal({
    title: "Add batch of links",
    body: `<div class="field"><label>One link per line</label><textarea id="b-links" placeholder="https://…"></textarea></div>
           <label class="check"><input type="checkbox" id="b-start" checked> Start downloads now</label>`,
    buttons: [{ label: "Cancel" }, { label: "Add", cls: "btn-primary", onClick: async (ov) => {
      const links = ov.querySelector("#b-links").value.split(/\s+/).filter(isUrl);
      if (!links.length) throw new Error("No valid links found.");
      const start = ov.querySelector("#b-start").checked;
      await api.addMany(links.map((url) => ({ url, start })));
      toast(`Added ${links.length} download${links.length > 1 ? "s" : ""}`);
      onDone?.();
    } }],
  });
}

// ---------------------------------------------------------------- Delete
export function deleteDialog(items, onDone) {
  const one = items.length === 1;
  const anyDone = items.some((d) => d.status === "complete");
  modal({
    title: one ? "Delete download" : `Delete ${items.length} downloads`,
    body: `<p style="margin:2px 0 12px;color:var(--text-2)">${one ? `Remove <b>${esc(items[0].filename)}</b> from the list?` : "Remove the selected downloads from the list?"}
           Unfinished parts are always removed.</p>
           ${anyDone ? `<label class="check"><input type="checkbox" id="del-file"> Also delete the downloaded file${one ? "" : "s"} from disk</label>` : ""}`,
    buttons: [{ label: "Cancel" }, { label: "Delete", cls: "btn btn-danger", primary: true, onClick: async (ov) => {
      const file = !!ov.querySelector("#del-file")?.checked;
      for (const d of items) await api.remove(d.id, file);
      onDone?.();
    } }],
  });
}

// ---------------------------------------------------------------- Scheduler
export function schedulerDialog(s) {
  modal({
    title: "Scheduler",
    body: `<label class="check"><input type="checkbox" id="sc-on" ${s.scheduler_enabled ? "checked" : ""}> Run the queue on a daily schedule</label>
      <div class="row2">
        <div class="field"><label>Start at</label><input type="time" id="sc-start" value="${esc(s.scheduler_start)}"></div>
        <div class="field"><label>Stop at</label><input type="time" id="sc-stop" value="${esc(s.scheduler_stop)}"></div>
      </div>
      <div class="hint" style="font-size:12px;color:var(--text-3)">At the start time every unfinished download in the queue resumes; at the stop time everything pauses. HyperGet must be running.</div>`,
    buttons: [{ label: "Cancel" }, { label: "Save", cls: "btn-primary", primary: true, onClick: async (ov) => {
      await api.settings({
        scheduler_enabled: ov.querySelector("#sc-on").checked,
        scheduler_start: ov.querySelector("#sc-start").value || "02:00",
        scheduler_stop: ov.querySelector("#sc-stop").value || "07:00",
      });
      toast("Scheduler saved");
    } }],
  });
}

// ---------------------------------------------------------------- Queue
export function queueDialog(state) {
  const s = state.settings;
  modal({
    title: "Queue",
    body: `<p style="margin:2px 0 12px;color:var(--text-2)"><b>${state.waiting}</b> waiting · <b>${state.active}</b> running</p>
      <div class="row2">
        <div class="field"><label>Downloads at the same time</label><input type="number" id="q-max" min="1" max="20" value="${s.max_active}"></div>
        <div class="field"><label>Connections per download</label><input type="number" id="q-conn" min="1" max="32" value="${s.connections}"></div>
      </div>`,
    buttons: [
      { label: "Stop queue", onClick: async () => { await api.stopAll(); } },
      { label: "Start queue", cls: "btn-primary", primary: true, onClick: async (ov) => {
        await api.settings({ max_active: +ov.querySelector("#q-max").value, connections: +ov.querySelector("#q-conn").value });
        await api.startQueue();
      } },
    ],
  });
}

// ---------------------------------------------------------------- Settings (tabbed)
const DAYS = ["M", "T", "W", "T", "F", "S", "S"];
const ICON = {
  general: "M4 6h16M4 12h16M4 18h16", connections: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18",
  rules: "M4 20V10M10 20V4M16 20v-7M22 20H2", video: "M4 6h12v12H4zM16 10l5-3v10l-5-3",
  browser: "M4 5h16v11H4zM9 20h6M12 16v4", licence: "M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z",
};

function ruleHtml(r, i) {
  return `<div class="rule edit" data-r="${i}">
    <span class="sw ${r.enabled ? "on" : ""}" data-k="enabled" title="On / off"></span>
    <input type="text" data-k="name" value="${esc(r.name)}" placeholder="Rule name">
    <button class="del" data-del="${i}" title="Remove rule">×</button>
    <div class="rule-row2">
      <div class="week">${DAYS.map((d, k) => `<i data-day="${k}" class="${r.days.includes(k) ? "on" : ""}">${d}</i>`).join("")}</div>
      <div class="times"><input type="time" data-k="start" value="${esc(r.start)}">to<input type="time" data-k="end" value="${esc(r.end)}">
        <input type="number" data-k="limit" min="0" value="${Math.round(r.limit / 1024)}" title="KB/s, 0 = unlimited">KB/s</div>
    </div></div>`;
}

export function settingsDialog(state, pane = "general") {
  const s = state.settings, f = state.features;
  let rules = s.speed_rules.map((r) => ({ ...r, days: [...r.days] }));
  let whenDone = s.when_done;
  const cap = state.data_cap;
  const nav = [["general", "General"], ["connections", "Connections"], ["rules", "Speed rules"], ["video", "Video sites"],
    ["browser", "Browser"], ["licence", "Licence"]];
  const dlg = modal({
    title: "Settings",
    size: "lg settings-dlg",
    body: `<div class="settings">
      <nav>${nav.map(([k, l]) => `<button class="nav-item${k === pane ? " sel" : ""}" data-pane="${k}"><span class="lbl"><svg class="ico" viewBox="0 0 24 24"><path d="${ICON[k]}"/></svg>${l}${k === "licence" ? '<span class="pro-pill">PRO</span>' : ""}</span><span class="count"></span></button>`).join("")}</nav>
      <div>
      <div class="pane" data-p="general">
        <h5>Downloads</h5>
        <div class="field"><label>Download folder</label><input type="text" id="o-dir" value="${esc(s.download_dir)}"></div>
        <label class="check"><input type="checkbox" id="o-cat" ${s.file_by_category ? "checked" : ""}> Sort into category folders (Compressed, Documents, Music, Programs, Video)</label>
        <label class="check"><input type="checkbox" id="o-clip" ${s.clipboard_watch ? "checked" : ""}> Offer to download links I copy (files and video pages)</label>
        <h5>Window</h5>
        <label class="check"><input type="checkbox" id="o-tray" ${s.close_to_tray ? "checked" : ""}> Keep running in the notification area when the window is closed</label>
        <label class="check"><input type="checkbox" id="o-notify" ${s.notify_complete ? "checked" : ""}> Show a notification when a download finishes or fails</label>
      </div>
      <div class="pane" data-p="connections" hidden>
        <h5>Connections</h5>
        <div class="row2">
          <div class="field"><label>Connections per download</label><input type="number" id="o-conn" min="1" max="32" value="${s.connections}"></div>
          <div class="field"><label>Downloads at the same time</label><input type="number" id="o-max" min="1" max="20" value="${s.max_active}"></div>
        </div>
        <div class="row2"><div class="field"><label>Speed limit (KB/s, 0 = unlimited)</label><input type="number" id="o-speed" min="0" value="${Math.round(s.speed_limit / 1024)}"></div></div>
        <h5>When a download fails</h5>
        <div class="row2">
          <div class="field"><label>Try again (times, 0 = off)</label><input type="number" id="o-retry" min="0" max="10" value="${s.auto_retry}"></div>
          <div class="field"><label>First retry after (seconds, then doubles)</label><input type="number" id="o-rdelay" min="5" max="3600" value="${s.retry_delay}"></div>
        </div>
        <div class="hint" style="font-size:11.5px;color:var(--text-3)">Only network problems are retried. Missing files and refused links are not.</div>
      </div>
      <div class="pane" data-p="rules" hidden>
        <h5>Speed rules</h5>
        <p style="margin:0 0 12px;font-size:12.5px;color:var(--text-3)">Keep the internet usable for others. The first rule that matches the day and time wins; outside them the normal speed limit applies.</p>
        <div id="o-rules"></div>
        <button class="btn" id="o-addrule" style="margin:4px 0 6px">+ Add rule</button>
        <h5>When all downloads finish</h5>
        <div class="seg" id="o-done">${[["nothing", "Do nothing"], ["sleep", "Sleep"], ["shutdown", "Shut down"], ["exit", "Exit HyperGet"]].map(([k, l]) =>
          `<span data-d="${k}" class="${k === whenDone ? "on" : ""}">${l}</span>`).join("")}</div>
        <div class="hint" style="font-size:11.5px;color:var(--text-3);margin-top:6px">Runs once, after a 60-second countdown you can cancel.</div>
        <h5>Monthly data cap</h5>
        <div class="row2"><div class="field"><label>Limit (GB, 0 = no cap)</label><input type="number" id="o-cap" min="0" value="${s.data_cap_gb}"></div>
          <div class="field"><label>When reached</label><select id="o-capact"><option value="pause" ${s.data_cap_action === "pause" ? "selected" : ""}>Pause all downloads</option><option value="warn" ${s.data_cap_action === "warn" ? "selected" : ""}>Only tell me</option></select></div></div>
        ${cap ? `<div class="callout">Used this month: <b>${bytes(cap.used, 1)} of ${bytes(cap.limit, 0)}</b>
          <div class="capbar ${cap.hit ? "full" : ""}"><i style="width:${Math.min(100, cap.used / cap.limit * 100).toFixed(1)}%"></i></div></div>`
          : `<div class="callout">Downloaded this month: <b>${bytes(state.month_bytes || 0, 1)}</b></div>`}
      </div>
      <div class="pane" data-p="video" hidden>
        <h5>Video sites</h5>
        <div class="msg info">
          Video sites (YouTube etc.): <b>${f.sites ? "enabled" : "not installed"}</b>${f.sites ? "" : " — run <code>pip install yt-dlp</code>"}<br>
          YouTube HD and 4K: <b>${f.youtube_hd ? "ready" : "not available"}</b>${f.youtube_hd ? "" : " — needs Deno and yt-dlp-ejs (included in the Windows installer)"}<br>
          FFmpeg (joining video and audio, MP3, subtitles): <b>${f.ffmpeg ? "found" : "not found"}</b>
        </div>
        <p style="font-size:12.5px;color:var(--text-3)">Paste a video or playlist link, or use the Download button the browser extension puts on videos. Only download videos you own or have permission to save.</p>
      </div>
      <div class="pane" data-p="browser" hidden>
        <h5>Browser extension</h5>
        <p style="font-size:12.5px;color:var(--text-2);margin-top:0">HyperGet connects to Chrome, Edge and Brave through its helper, the same way IDM does. It registers itself each time HyperGet starts.</p>
        <button class="btn" data-cmd-x="extension">How to add the extension…</button>
      </div>
      <div class="pane" data-p="licence" hidden>
        <h5>HyperGet Pro</h5>
        <div class="callout">You're using the <b>Pro preview</b>: every Pro feature is free while HyperGet is new. When paid plans start, Free stays free.</div>
        <p style="font-size:12.5px;color:var(--text-3)">Pro: playlists and channels, 4K, subtitles, MP3, speed rules, when-done actions, data cap, statistics and more.</p>
        <button class="btn" data-cmd-x="plans">See the plans…</button>
      </div>
      </div>
    </div>`,
    buttons: [{ label: "Cancel" }, { label: "Save", cls: "btn-primary", primary: true, onClick: async (ov) => {
      readRules(ov);
      await api.settings({
        download_dir: ov.querySelector("#o-dir").value.trim() || s.download_dir,
        file_by_category: ov.querySelector("#o-cat").checked,
        clipboard_watch: ov.querySelector("#o-clip").checked,
        close_to_tray: ov.querySelector("#o-tray").checked,
        notify_complete: ov.querySelector("#o-notify").checked,
        connections: +ov.querySelector("#o-conn").value,
        max_active: +ov.querySelector("#o-max").value,
        speed_limit: Math.max(0, +ov.querySelector("#o-speed").value) * 1024,
        auto_retry: +ov.querySelector("#o-retry").value,
        retry_delay: +ov.querySelector("#o-rdelay").value,
        speed_rules: rules,
        data_cap_gb: Math.max(0, +ov.querySelector("#o-cap").value || 0),
        data_cap_action: ov.querySelector("#o-capact").value,
      });
      if (whenDone !== s.when_done) await api.whenDone(whenDone);
      toast("Settings saved");
    } }],
  });
  const ov = dlg.el;
  const box = ov.querySelector("#o-rules");

  function readRules(root) {
    root.querySelectorAll(".rule.edit").forEach((row) => {
      const r = rules[+row.dataset.r];
      if (!r) return;
      r.name = row.querySelector("[data-k=name]").value.trim() || "Speed rule";
      r.start = row.querySelector("[data-k=start]").value || r.start;
      r.end = row.querySelector("[data-k=end]").value || r.end;
      r.limit = Math.max(0, +row.querySelector("[data-k=limit]").value || 0) * 1024;
    });
  }
  function drawRules() {
    box.innerHTML = rules.length ? rules.map(ruleHtml).join("") : `<div class="conn-note" style="margin-bottom:8px">No rules yet.</div>`;
    box.querySelectorAll(".rule.edit").forEach((row) => {
      const r = rules[+row.dataset.r];
      row.querySelector("[data-k=enabled]").onclick = (e) => { r.enabled = !r.enabled; e.target.classList.toggle("on", r.enabled); };
      row.querySelectorAll("[data-day]").forEach((d) => d.onclick = () => {
        const k = +d.dataset.day;
        r.days = r.days.includes(k) ? r.days.filter((x) => x !== k) : [...r.days, k].sort();
        d.classList.toggle("on", r.days.includes(k));
      });
      row.querySelector("[data-del]").onclick = () => { readRules(ov); rules.splice(+row.dataset.r, 1); drawRules(); };
    });
  }
  drawRules();
  ov.querySelector("#o-addrule").onclick = () => {
    readRules(ov);
    if (rules.length >= 10) return toast("Up to 10 rules");
    rules.push({ name: rules.length ? "Speed rule" : "Working hours", enabled: true, days: [0, 1, 2, 3, 4], start: "08:00", end: "17:00", limit: 1024 * 1024 });
    drawRules();
  };
  ov.querySelectorAll("#o-done span").forEach((sp) => sp.onclick = () => {
    whenDone = sp.dataset.d;
    ov.querySelectorAll("#o-done span").forEach((x) => x.classList.toggle("on", x === sp));
  });
  ov.querySelectorAll("[data-pane]").forEach((b) => b.onclick = () => {
    ov.querySelectorAll("[data-pane]").forEach((x) => x.classList.toggle("sel", x === b));
    ov.querySelectorAll(".pane").forEach((p) => { p.hidden = p.dataset.p !== b.dataset.pane; });
  });
  ov.querySelectorAll(".pane").forEach((p) => { p.hidden = p.dataset.p !== pane; });
  ov.querySelectorAll("[data-cmd-x]").forEach((b) => b.onclick = () => { dlg.close(); window.hgCommand?.(b.dataset.cmdX); });
}

// ---------------------------------------------------------------- Plans
// Planned prices; payments aren't open yet, so nothing here charges anyone.
const PLANS = { pro: "TSh 25,000", proUsd: "≈ $10", life: "TSh 60,000", lifeUsd: "≈ $24" };

export function plansDialog() {
  modal({
    title: "HyperGet Pro",
    size: "xl",
    body: `<p style="margin:0 0 20px;color:var(--text-3);font-size:13px">Free stays free forever. Pro adds the tools for people who download every day.
      <b style="color:var(--text-2)">During the preview every Pro feature is free.</b></p>
    <div class="plans">
      <div class="plan"><h4>Free</h4><div class="price">TSh 0</div><div class="alt">For everyone</div>
        <ul><li>Multi-connection downloads with resume</li><li>Queue, scheduler, link grabber</li><li>Browser extension</li><li>Videos and streams</li>
          <li class="no">Playlists and channels</li><li class="no">Subtitles and MP3</li><li class="no">Speed rules, when-done, data cap</li><li class="no">Statistics</li></ul>
        <button class="btn" disabled>Free forever</button></div>
      <div class="plan best"><span class="ribbon">MOST POPULAR</span><h4>Pro · 1 year</h4><div class="price">${PLANS.pro} <small>/ year</small></div><div class="alt">${PLANS.proUsd} · 3 PCs · planned price</div>
        <ul><li>Everything in Free</li><li>Playlists, channels and 4K</li><li>Subtitles and MP3</li><li>Speed rules by day and hour</li>
          <li>When-done: sleep, shut down, exit</li><li>Monthly data cap</li><li>Statistics</li><li>Priority support</li></ul>
        <button class="btn-primary" disabled>Included in the preview</button></div>
      <div class="plan"><h4>Pro · Lifetime</h4><div class="price">${PLANS.life}</div><div class="alt">${PLANS.lifeUsd} · pay once · 3 PCs</div>
        <ul><li>Everything in Pro</li><li>All future versions</li><li>Move the licence to a new PC</li><li>Early access to new features</li></ul>
        <button class="btn" disabled>Coming soon</button></div>
    </div>
    <div class="pay">Planned payment: <span class="m">M-Pesa</span><span class="m">Tigo Pesa</span><span class="m">Airtel Money</span><span class="m">Visa / Mastercard</span></div>`,
    left: "Prices are planned and may change.",
    buttons: [{ label: "Close", cls: "btn-primary", primary: true }],
  });
}

// ---------------------------------------------------------------- Grabber
export function grabberDialog(onDone) {
  let found = [];
  const dlg = modal({
    title: "Grabber",
    wide: true,
    body: `
      <div class="field"><label>Web page to scan for downloadable files</label>
        <div style="display:flex;gap:8px"><input type="url" id="g-url" placeholder="https://example.com/downloads/"><button class="btn" id="g-scan">Scan</button></div></div>
      <div id="g-res"></div>`,
    buttons: [{ label: "Close" }, { label: "Download selected", cls: "btn-primary", onClick: async (ov) => {
      const picked = [...ov.querySelectorAll(".grab-item input:checked")].map((c) => found[+c.dataset.i]);
      if (!picked.length) throw new Error("Select at least one file.");
      await api.addMany(picked.map((f) => ({ url: f.url, page_url: ov.querySelector("#g-url").value.trim() })));
      toast(`Added ${picked.length} download${picked.length > 1 ? "s" : ""}`);
      onDone?.();
    } }],
  });
  const ov = dlg.el, res = ov.querySelector("#g-res");
  ov.querySelector("#g-scan").onclick = async () => {
    const url = ov.querySelector("#g-url").value.trim();
    if (!isUrl(url)) { res.innerHTML = `<div class="msg error">Enter a valid http(s) page address.</div>`; return; }
    res.innerHTML = `<div class="msg info"><span class="spinner"></span>Scanning page…</div>`;
    try {
      found = (await api.grab(url)).links;
      if (!found.length) { res.innerHTML = `<div class="msg info">No downloadable files found on that page.</div>`; return; }
      res.innerHTML = `<label class="check"><input type="checkbox" id="g-all"> Select all (${found.length})</label>
        <div class="grab-list">${found.map((f, i) => `
          <label class="grab-item"><input type="checkbox" data-i="${i}"><span class="badge">${esc(f.badge)}</span>
          <div style="min-width:0"><div class="n">${esc(f.filename)}</div><div class="u">${esc(f.url)}</div></div></label>`).join("")}</div>`;
      res.querySelector("#g-all").onchange = (e) => res.querySelectorAll(".grab-item input").forEach((c) => c.checked = e.target.checked);
    } catch (e) {
      res.innerHTML = `<div class="msg error">${esc(e.message)}</div>`;
    }
  };
}

// ---------------------------------------------------------------- Info dialogs
export function aboutDialog(version) {
  modal({
    title: "About",
    body: `<div class="about">
      <img class="logo-lg" src="icons/logo.svg" alt="">
      <div style="font-weight:700;font-size:15px">HyperGet Downloader</div>
      <p>Version ${esc(version || "0.1.0")}</p>
      <p>Multi-connection downloads with resume, HLS streams with quality selection,<br>scheduler, queue, link grabber and browser integration.</p></div>`,
    buttons: [{ label: "Close", cls: "btn-primary", primary: true }],
  });
}

export function extensionDialog() {
  modal({
    title: "Browser extension",
    body: `<ol class="steps">
        <li>Open <code>chrome://extensions</code> (or <code>edge://extensions</code>) and turn on <b>Developer mode</b>.</li>
        <li>Click <b>Load unpacked</b> and choose the <code>extension</code> folder from HyperGet.</li>
        <li>On pages with video a <b>Download</b> button appears over the player; pick a quality and it's sent here. If HyperGet is closed, the browser starts it.</li>
      </ol>
      <div class="msg info">The browser talks to HyperGet through its helper, the same way IDM connects. HyperGet registers it with Chrome, Edge and Brave each time it starts; nothing to set up.</div>`,
    buttons: [{ label: "Close", cls: "btn-primary", primary: true }],
  });
}

export function sitesDialog(enabled) {
  modal({
    title: "Video site support",
    body: enabled
      ? `<div class="msg info">Enabled. Paste a video page link (or use the browser extension) to choose a quality.</div>
         <p style="font-size:12.5px;color:var(--text-3)">Respect each site's terms: only download videos you own or have permission to save.</p>`
      : `<p style="font-size:13px;color:var(--text-2);margin-top:2px">Downloading from video sites such as YouTube uses the open-source <b>yt-dlp</b> extractor, which isn't installed.</p>
         <ol class="steps"><li>Run <code>pip install yt-dlp</code></li><li>Restart HyperGet.</li></ol>
         <p style="font-size:12.5px;color:var(--text-3)">Respect each site's terms: only download videos you own or have permission to save. DRM-protected services are not supported.</p>`,
    buttons: [{ label: "Close", cls: "btn-primary", primary: true }],
  });
}
