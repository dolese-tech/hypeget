import { api } from "./api.js";
import { bytes, esc, isUrl } from "./format.js";

export function toast(text, ms = 2600) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

export function modal({ title, body, buttons = [], wide = false, left = "" }) {
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `
    <div class="dialog ${wide ? "wide" : ""}" role="dialog" aria-modal="true">
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

// ---------------------------------------------------------------- Add URL
export function addUrlDialog(prefill = "", onDone) {
  let info = null, chosen = null, seq = 0;
  const dlg = modal({
    title: "Add URL",
    wide: true,
    body: `
      <div class="field"><label>Address</label><input type="url" id="au-url" placeholder="https://example.com/file.zip or a video page / .m3u8 link" value="${esc(prefill)}"></div>
      <div id="au-info"></div>
      <div class="field"><label>Save as</label><input type="text" id="au-name" placeholder="Detected automatically"></div>
      <label class="check"><input type="checkbox" id="au-start" checked> Start download now</label>`,
    buttons: [
      { label: "Cancel" },
      { label: "Download", cls: "btn-primary", primary: true, onClick: async (ov) => {
        const url = ov.querySelector("#au-url").value.trim();
        if (!isUrl(url)) throw new Error("Enter a valid http(s) link.");
        const name = ov.querySelector("#au-name").value.trim();
        const item = { url, start: ov.querySelector("#au-start").checked };
        if (info && chosen) {
          item.kind = info.kind;
          item.title = info.kind === "http" ? "" : info.title;
          item.quality = chosen.quality || "";
          item.options = { variant_url: chosen.variant_url, audio_url: chosen.audio_url, format: chosen.format };
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

  async function check() {
    const url = urlIn.value.trim();
    info = chosen = null;
    if (!isUrl(url)) { box.innerHTML = ""; return; }
    const my = ++seq;
    box.innerHTML = `<div class="msg info"><span class="spinner"></span>Checking link…</div>`;
    try {
      const res = await api.inspect(url);
      if (my !== seq) return;
      info = res;
      chosen = res.options[0];
      renderInfo();
    } catch (e) {
      if (my !== seq) return;
      box.innerHTML = `<div class="msg error">${esc(e.message)} — you can still try to download it.</div>`;
    }
  }

  function suggestedName() {
    if (!info) return "";
    if (info.kind === "http") return info.filename;
    const ext = chosen?.quality === "audio" ? ".m4a" : ".mp4";
    const q = chosen?.quality && chosen.quality !== "audio" ? `_${chosen.quality}` : "";
    return `${info.title}${q}${ext}`;
  }

  function renderInfo() {
    const opts = info.options;
    const isVideo = info.kind !== "http";
    let html = "";
    if (isVideo) {
      const dur = info.duration ? ` · ${Math.floor(info.duration / 60)}:${String(Math.round(info.duration % 60)).padStart(2, "0")}` : "";
      html += `<div class="field"><label>Quality <span style="color:var(--text-3);font-weight:400">— ${esc(info.title)}${dur}</span></label>
        <div class="qualities">${opts.map((o, i) => `
          <label class="quality ${o === chosen ? "sel" : ""}" data-i="${i}">
            <input type="radio" name="q" ${o === chosen ? "checked" : ""}>
            <span class="q">${esc(o.label)}</span><span class="d">${esc(o.detail || "")}</span>
            <span class="s">${o.est_size ? "≈ " + bytes(o.est_size) : ""}</span>
          </label>`).join("")}</div></div>`;
    } else {
      const o = opts[0];
      html += `<div class="msg info">${esc(info.filename)} · ${o.est_size ? bytes(o.est_size) : "size unknown"} · ${esc(o.detail)}</div>`;
    }
    box.innerHTML = html;
    box.querySelectorAll(".quality").forEach((q) => q.onclick = () => {
      chosen = opts[+q.dataset.i];
      box.querySelectorAll(".quality").forEach((x) => x.classList.toggle("sel", x === q));
      q.querySelector("input").checked = true;
      const s = suggestedName();
      if (!nameIn.dataset.touched) nameIn.value = s;
      info.suggested = s;
    });
    info.suggested = suggestedName();
    if (!nameIn.dataset.touched) nameIn.value = info.suggested;
  }

  let timer;
  urlIn.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(check, 450); });
  nameIn.addEventListener("input", () => { nameIn.dataset.touched = "1"; });
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

// ---------------------------------------------------------------- Options
export function optionsDialog(state) {
  const s = state.settings, f = state.features;
  modal({
    title: "Options",
    wide: true,
    body: `
      <div class="field"><label>Download folder</label><input type="text" id="o-dir" value="${esc(s.download_dir)}"></div>
      <label class="check"><input type="checkbox" id="o-cat" ${s.file_by_category ? "checked" : ""}> Sort into category folders (Compressed, Documents, Music, Programs, Video)</label>
      <div class="row2">
        <div class="field"><label>Connections per download</label><input type="number" id="o-conn" min="1" max="32" value="${s.connections}"></div>
        <div class="field"><label>Downloads at the same time</label><input type="number" id="o-max" min="1" max="20" value="${s.max_active}"></div>
      </div>
      <div class="row2">
        <div class="field"><label>Speed limit (KB/s, 0 = unlimited)</label><input type="number" id="o-speed" min="0" value="${Math.round(s.speed_limit / 1024)}"></div>
        <div class="field"><label>Browser extension port</label><input type="number" id="o-port" min="1024" max="65535" value="${s.api_port}">
          <div class="hint">Takes effect after restarting HyperGet.</div></div>
      </div>
      <div class="msg info">
        Video sites (YouTube etc.): <b>${f.sites ? "enabled" : "not installed"}</b>${f.sites ? "" : " — run <code>pip install yt-dlp</code>"}<br>
        FFmpeg (merging HLS audio/video into MP4): <b>${f.ffmpeg ? "found" : "not found"}</b>
      </div>`,
    buttons: [{ label: "Cancel" }, { label: "Save", cls: "btn-primary", primary: true, onClick: async (ov) => {
      await api.settings({
        download_dir: ov.querySelector("#o-dir").value.trim() || s.download_dir,
        file_by_category: ov.querySelector("#o-cat").checked,
        connections: +ov.querySelector("#o-conn").value,
        max_active: +ov.querySelector("#o-max").value,
        speed_limit: Math.max(0, +ov.querySelector("#o-speed").value) * 1024,
        api_port: +ov.querySelector("#o-port").value,
      });
      toast("Options saved");
    } }],
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
      <div class="logo-lg"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/></svg></div>
      <div style="font-weight:700;font-size:15px">HyperGet Downloader</div>
      <p>Version ${esc(version || "0.1.0")}</p>
      <p>Multi-connection downloads with resume, HLS streams with quality selection,<br>scheduler, queue, link grabber and browser integration.</p></div>`,
    buttons: [{ label: "Close", cls: "btn-primary", primary: true }],
  });
}

export function extensionDialog(port) {
  modal({
    title: "Browser extension",
    body: `<ol class="steps">
        <li>Open <code>chrome://extensions</code> (or <code>edge://extensions</code>) and turn on <b>Developer mode</b>.</li>
        <li>Click <b>Load unpacked</b> and choose the <code>extension</code> folder from HyperGet.</li>
        <li>Keep HyperGet running. On pages with video a <b>Download</b> button appears over the player; pick a quality and it's sent here.</li>
      </ol>
      <div class="msg info">The extension talks to HyperGet on <code>127.0.0.1:${port}</code>. Only extensions can use this port; normal websites are blocked.</div>`,
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
