import { added, bytes, esc, eta, pct, speed, statusLabel } from "./format.js";

const ACTIVE = new Set(["downloading", "connecting", "merging"]);

export function filterRows(list, filter, query) {
  const q = query.trim().toLowerCase();
  return list.filter((d) => {
    if (q && !/^https?:\/\//.test(q) &&
        !(d.filename.toLowerCase().includes(q) || d.host.toLowerCase().includes(q) ||
          (d.title || "").toLowerCase().includes(q) || (d.group || "").toLowerCase().includes(q))) return false;
    if (filter === "all" || filter === "grabber" || filter === "stats") return true;
    if (filter.startsWith("cat:")) return d.category === filter.slice(4);
    if (filter.startsWith("group:")) return d.group === filter.slice(6);
    if (filter === "finished") return d.status === "complete";
    if (filter === "unfinished") return d.status !== "complete";
    if (filter === "queues") return d.status === "queued" || (d.in_queue && d.status !== "complete");
    return true;
  });
}

const sorters = {
  name: (a, b) => a.filename.localeCompare(b.filename),
  size: (a, b) => (a.size || 0) - (b.size || 0),
  progress: (a, b) => a.progress - b.progress,
  speed: (a, b) => a.speed - b.speed,
  eta: (a, b) => (a.eta ?? 1e12) - (b.eta ?? 1e12),
  added: (a, b) => a.added - b.added,
};

export function sortRows(list, sort) {
  if (!sort.key) return list;
  const f = sorters[sort.key];
  const out = [...list].sort(f);
  return sort.dir < 0 ? out.reverse() : out;
}

/** Playlist videos are shown under one row per playlist (when the view isn't that playlist). */
export function groupRows(rows, collapsed, enabled) {
  if (!enabled) return rows.map((d) => ({ type: "dl", d }));
  const members = new Map();
  for (const d of rows) if (d.group) (members.get(d.group) || members.set(d.group, []).get(d.group)).push(d);
  const out = [], placed = new Set();
  for (const d of rows) {
    const list = d.group ? members.get(d.group) : null;
    if (!list || list.length < 2) { out.push({ type: "dl", d }); continue; }
    if (placed.has(d.group)) continue;
    placed.add(d.group);
    const open = !collapsed.has(d.group);
    out.push({ type: "group", name: d.group, list, open });
    if (open) for (const m of list) out.push({ type: "dl", d: m, child: true });
  }
  return out;
}

export function groupSummary(list) {
  const done = list.filter((d) => d.status === "complete").length;
  const running = list.filter((d) => ACTIVE.has(d.status)).length;
  const failed = list.filter((d) => d.status === "error").length;
  const size = list.reduce((s, d) => s + (d.size || 0), 0);
  const got = list.reduce((s, d) => s + (d.status === "complete" ? (d.size || 0) : d.downloaded), 0);
  const spd = list.reduce((s, d) => s + (d.status === "downloading" ? d.speed : 0), 0);
  const progress = size ? got / size : done / list.length;
  let status = "queued";
  if (done === list.length) status = "complete";
  else if (running) status = "downloading";
  else if (failed) status = "error";
  else if (list.every((d) => ["paused", "complete"].includes(d.status))) status = "paused";
  const parts = [`${done} of ${list.length} done`];
  if (running) parts.push(`${running} downloading`);
  if (failed) parts.push(`${failed} failed`);
  return { done, running, size, progress, speed: spd, eta: spd > 0 && size ? (size - got) / spd : null, status,
    label: done === list.length ? `Complete · ${list.length} videos` : parts.join(" · "),
    added: Math.min(...list.map((d) => d.added)) };
}

function rowHtml() {
  return `
    <div class="cell-name"><span class="badge"></span><div class="name-wrap"><div class="fname"><span class="t"></span><span class="chips"></span></div><div class="fhost"></div></div></div>
    <div class="cell c-size"></div>
    <div class="prog"><div class="bar"><i></i></div><div class="label"></div></div>
    <div class="cell c-speed"></div>
    <div class="cell c-eta col-eta"></div>
    <div class="cell c-added col-added"></div>`;
}

function set(el, sel, text) {
  const n = el.querySelector(sel);
  if (n.textContent !== text) n.textContent = text;
}

function setHtml(el, sel, html) {
  const n = el.querySelector(sel);
  if (n.dataset.h !== html) { n.innerHTML = html; n.dataset.h = html; }
}

export function chipsFor(d) {
  const c = [];
  if (d.status === "downloading" && d.connections.length > 1) c.push(`<span class="chip">${d.connections.length}×</span>`);
  if (d.kind !== "http" && d.quality) {
    const q = d.quality === "audio" ? (d.filename.toLowerCase().endsWith(".mp3") ? "MP3" : "Audio") : d.quality;
    c.push(`<span class="chip q">${esc(q)}</span>`);
  }
  if (d.subtitles) c.push(`<span class="chip g">SRT</span>`);
  if (d.status === "error" && d.retry_in != null) c.push(`<span class="chip o">Auto-retry</span>`);
  return c.join("");
}

function fillDownload(el, d, selected, child) {
  const showSpeed = d.status === "downloading";
  el.className = `grid-row row${child ? " child" : ""}${selected.has(d.id) ? " sel" : ""}`;
  const badge = el.querySelector(".badge");
  if (d.thumbnail) {
    badge.className = "badge thumb";
    const bg = `url("${d.thumbnail.replace(/"/g, "%22")}")`;
    if (badge.style.backgroundImage !== bg) badge.style.backgroundImage = bg;
    badge.textContent = "";
  } else {
    badge.className = "badge";
    badge.style.backgroundImage = "";
    set(el, ".badge", d.badge);
  }
  set(el, ".fname .t", d.filename || d.title || d.url);
  el.querySelector(".fname").title = d.filename;
  setHtml(el, ".chips", chipsFor(d));
  set(el, ".fhost", d.group && !child ? `${d.host} · ${d.group}` : d.host);
  set(el, ".c-size", d.size ? bytes(d.size) : "—");
  set(el, ".c-speed", showSpeed ? speed(d.speed) : "—");
  set(el, ".c-eta", showSpeed ? eta(d.eta) : "—");
  set(el, ".c-added", added(d.added));
  el.querySelector(".c-speed").classList.toggle("muted", !showSpeed);
  el.querySelector(".c-eta").classList.toggle("muted", !showSpeed);
  const prog = el.querySelector(".prog");
  prog.className = `prog st-${d.status}` + ((d.status === "connecting" || (ACTIVE.has(d.status) && !d.size && d.kind !== "hls")) ? " indeterminate" : "");
  const p = d.status === "complete" ? 1 : d.status === "error" ? Math.max(d.progress, 0.17) : d.progress;
  el.querySelector(".bar > i").style.width = `${(p * 100).toFixed(2)}%`;
  set(el, ".label", statusLabel(d));
  el.querySelector(".label").title = statusLabel(d);
}

function fillGroup(el, g) {
  const s = groupSummary(g.list);
  el.className = "grid-row row group";
  const badge = el.querySelector(".badge");
  badge.className = "badge";
  badge.style.backgroundImage = "";
  set(el, ".badge", `${g.open ? "▾" : "▸"} ${g.list.length}`);
  set(el, ".fname .t", g.name);
  el.querySelector(".fname").title = g.name;
  setHtml(el, ".chips", `<span class="chip q">PLAYLIST</span>`);
  const q = g.list[0].quality;
  set(el, ".fhost", `${g.list[0].host} · ${g.list.length} videos${q ? " · " + (q === "audio" ? "audio" : q) : ""}`);
  set(el, ".c-size", s.size ? bytes(s.size) : "—");
  set(el, ".c-speed", s.speed > 0 ? speed(s.speed) : "—");
  set(el, ".c-eta", s.speed > 0 ? eta(s.eta) : "—");
  set(el, ".c-added", added(s.added));
  el.querySelector(".c-speed").classList.toggle("muted", !(s.speed > 0));
  el.querySelector(".c-eta").classList.toggle("muted", !(s.speed > 0));
  el.querySelector(".prog").className = `prog st-${s.status}`;
  el.querySelector(".bar > i").style.width = `${(s.progress * 100).toFixed(2)}%`;
  set(el, ".label", s.status === "downloading" ? `${pct(s.progress)} · ${s.label}` : s.label);
}

export function renderTable(tbody, items, selected, emptyMsg) {
  const existing = new Map([...tbody.querySelectorAll(".row")].map((r) => [r.dataset.id, r]));
  if (!items.length) {
    tbody.innerHTML = `<div class="empty">${emptyMsg}</div>`;
    return;
  }
  tbody.querySelector(".empty")?.remove();
  let prev = null;
  for (const it of items) {
    const key = it.type === "group" ? `g:${it.name}` : it.d.id;
    let el = existing.get(key);
    if (!el) {
      el = document.createElement("div");
      el.dataset.id = key;
      el.innerHTML = rowHtml();
    }
    existing.delete(key);
    if (it.type === "group") fillGroup(el, it);
    else fillDownload(el, it.d, selected, it.child);
    const want = prev ? prev.nextSibling : tbody.firstChild;
    if (want !== el) tbody.insertBefore(el, want);
    prev = el;
  }
  for (const el of existing.values()) el.remove();
}

export { esc };
