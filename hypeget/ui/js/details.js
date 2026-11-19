import { bytes, esc } from "./format.js";

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

export function renderDetails(el, d) {
  if (!d) {
    el.innerHTML = `<div class="conn-note" style="grid-column:1/-1;align-self:center;text-align:center">Select a download to see its details.</div>`;
    return;
  }
  let second = ["Resume", resumeText(d)];
  if (d.status === "error") second = ["Error", d.error, "err"];
  else if (d.quality) second = ["Quality", `${d.quality === "audio" ? "Audio only" : d.quality}${d.kind === "hls" ? " · HLS stream" : ""}`];
  const rows = [
    ["Downloaded", downloadedText(d)],
    second,
    ["Connections", connectionsText(d)],
    ["Save to", d.save_dir],
  ];

  let conns;
  if (d.connections.length) {
    conns = `<div class="conns">${d.connections.slice(0, 8).map((p, i) => `
      <div class="conn"><span>#${i + 1}</span><div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div><span class="pct">${Math.floor(p * 100)}%</span></div>`).join("")}</div>`;
  } else if (d.status === "complete") {
    conns = `<div class="conn-note">Finished${d.finished_at ? " " + new Date(d.finished_at * 1000).toLocaleString() : ""}.</div>`;
  } else if (d.status === "error") {
    conns = `<div class="conn-note">Download stopped with an error. Use Resume to retry${d.resumable ? " from where it left off" : ""}.</div>`;
  } else {
    conns = `<div class="conn-note">No active connections.</div>`;
  }

  const actions = d.status === "complete"
    ? `<button class="link-btn" data-cmd="open">Open</button><button class="link-btn" data-cmd="folder">Folder</button>`
    : ["downloading", "connecting", "merging", "queued"].includes(d.status)
      ? `<button class="link-btn" data-cmd="pause">Pause</button>`
      : `<button class="link-btn" data-cmd="resume">Resume</button>`;

  el.innerHTML = `
    <div style="min-width:0">
      <div class="d-title" title="${esc(d.filename)}">${esc(d.filename || d.title)}</div>
      <div class="d-url" title="${esc(d.url)}">${esc(d.url.replace(/^https?:\/\//, ""))}</div>
      <dl class="kv">${rows.map(([k, v, c]) => `<dt>${k}</dt><dd class="${c || ""}" title="${esc(v)}">${esc(v)}</dd>`).join("")}</dl>
    </div>
    <div style="min-width:0">
      <div class="conn-head"><span>CONNECTIONS</span><span class="actions">${actions}</span></div>
      ${conns}
    </div>`;
}
