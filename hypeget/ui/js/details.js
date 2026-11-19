import { bytes, esc, speed } from "./format.js";

function resumeText(d) {
  if (d.resumable === true) return "Supported";
  if (d.resumable === false) return "Not supported by server";
  return "Checking…";
}

function connectionsText(d) {
  const n = d.connections.length;
  if (d.status === "downloading") return `${n} active`;
  if (d.kind === "hls" && d.parts_total) return `${d.max_connections} max · ${d.parts_done}/${d.parts_total} segments`;
  return `${d.max_connections} max`;
}

function downloadedText(d) {
  if (d.status === "complete") return d.size ? bytes(d.size) : "—";
  const total = d.size ? ` of ${bytes(d.size)}${d.size_exact ? "" : " (est.)"}` : "";
  return `${bytes(d.downloaded, d.downloaded > 1024 ** 3 ? 2 : undefined)}${total}`;
}

function graph(history) {
  const W = 420, H = 92;
  const vals = history.length ? history : [0];
  const max = Math.max(1024 * 1024, ...vals) * 1.15;
  const step = W / 59;
  const x0 = W - (vals.length - 1) * step;
  const pts = vals.map((v, i) => [x0 + i * step, H - 4 - (v / max) * (H - 12)]);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const grid = [0.25, 0.5, 0.75].map((f) => `<line x1="0" x2="${W}" y1="${H * f}" y2="${H * f}" stroke="var(--border)" stroke-dasharray="3 3"/>`).join("");
  const top = max * (1 - 0.25 * (H / (H - 12)));   // value at the upper grid line (approx.)
  const label = `<text x="${W - 2}" y="${H * 0.25 - 3}" text-anchor="end" font-size="9.5" fill="var(--text-4)">${bytes(top, 1)}/s</text>`;
  const last = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${grid}${label}
    <defs><linearGradient id="gf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".28"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs>
    ${vals.length > 1 ? `<polygon points="${pts[0][0].toFixed(1)},${H} ${line} ${W},${H}" fill="url(#gf)"/><polyline points="${line}" fill="none" stroke="var(--blue)" stroke-width="1.8" vector-effect="non-scaling-stroke"/>` : ""}
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3" fill="var(--blue)"/></svg>`;
}

function fileMap(map) {
  return `<div class="segmap">${map.map((c) => `<i class="${c === 2 ? "d" : c === 1 ? "a" : ""}"></i>`).join("")}</div>
    <div class="seg-note"><span>Done</span><span class="a">Downloading</span><span class="w">Waiting</span></div>`;
}

export function renderDetails(el, d) {
  if (!d) {
    el.innerHTML = `<div class="conn-note" style="grid-column:1/-1;align-self:center;text-align:center">Select a download to see its details.</div>`;
    return;
  }
  let second = ["Resume", resumeText(d)];
  if (d.status === "error") second = ["Error", d.error, "err"];
  else if (d.quality) second = ["Quality", `${d.quality === "audio" ? "Audio only" : d.quality}${d.kind === "hls" ? " · HLS stream" : ""}`];
  const extra = [];
  if (d.subtitles) extra.push(["Subtitles", d.subtitles.replace(/^auto:/, "") + (d.subtitles.startsWith("auto:") ? " (automatic)" : "")]);
  if (d.group) extra.push(["Playlist", d.group]);
  extra.push(["Connections", connectionsText(d)]);
  const rows = [["Downloaded", downloadedText(d)], second, ...extra.slice(0, 2), ["Save to", d.save_dir]];

  const actions = d.status === "complete"
    ? `<button class="link-btn" data-cmd="open">Open</button><button class="link-btn" data-cmd="folder">Folder</button>`
    : ["downloading", "connecting", "merging", "queued"].includes(d.status)
      ? `<button class="link-btn" data-cmd="pause">Pause</button>`
      : `<button class="link-btn" data-cmd="resume">Resume</button>`;

  const h = d.history || [];
  const avg = h.length ? h.reduce((a, b) => a + b, 0) / h.length : 0;
  const peak = h.length ? Math.max(...h) : 0;
  let middle;
  if (d.status === "complete") {
    middle = `<div class="conn-note">Finished${d.finished_at ? " " + new Date(d.finished_at * 1000).toLocaleString() : ""}.</div>`;
  } else if (d.status === "error") {
    middle = `<div class="conn-note">${d.retry_in != null ? `HyperGet will try again in ${d.retry_in} s.` : `Download stopped with an error. Use Resume to retry${d.resumable ? " from where it left off" : ""}.`}</div>`;
  } else if (h.length > 1) {
    middle = `${graph(h)}<div class="legend"><span>Now <b>${speed(d.speed)}</b></span><span>Average <b>${speed(avg)}</b></span><span>Peak <b>${speed(peak)}</b></span></div>`;
  } else {
    middle = `<div class="conn-note">${["downloading", "connecting"].includes(d.status) ? "Measuring speed…" : "Not downloading right now."}</div>`;
  }

  let right;
  if (d.file_map) {
    const n = d.connections.length;
    right = `<div class="conn-head"><span>FILE MAP${n ? ` · ${n} CONNECTION${n > 1 ? "S" : ""}` : ""}</span></div>${fileMap(d.file_map)}`;
  } else if (d.connections.length) {
    right = `<div class="conn-head"><span>CONNECTIONS</span></div><div class="conns" style="grid-template-columns:1fr">${d.connections.slice(0, 4).map((p, i) => `
      <div class="conn"><span>#${i + 1}</span><div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div><span class="pct">${Math.floor(p * 100)}%</span></div>`).join("")}</div>`;
  } else {
    right = `<div class="conn-head"><span>FILE MAP</span></div><div class="conn-note">${d.kind === "site" ? "Video sites download in parts; the map shows for direct links and streams." : "Shown once the file size is known."}</div>`;
  }

  el.innerHTML = `
    <div style="min-width:0">
      <div class="d-title" title="${esc(d.filename)}">${esc(d.filename || d.title)}</div>
      <div class="d-url" title="${esc(d.url)}">${esc(d.url.replace(/^https?:\/\//, ""))}</div>
      <dl class="kv">${rows.map(([k, v, c]) => `<dt>${k}</dt><dd class="${c || ""}" title="${esc(v)}">${esc(v)}</dd>`).join("")}</dl>
    </div>
    <div class="graph-wrap"><div class="conn-head"><span>SPEED · LAST 60 S</span><span class="actions">${actions}</span></div>${middle}</div>
    <div style="min-width:0">${right}</div>`;
}
