import { added, bytes, esc, eta, speed, statusLabel } from "./format.js";

const ACTIVE = new Set(["downloading", "connecting", "merging"]);

export function filterRows(list, filter, query) {
  const q = query.trim().toLowerCase();
  return list.filter((d) => {
    if (q && !/^https?:\/\//.test(q) &&
        !(d.filename.toLowerCase().includes(q) || d.host.toLowerCase().includes(q) || (d.title || "").toLowerCase().includes(q))) return false;
    if (filter === "all" || filter === "grabber") return true;
    if (filter.startsWith("cat:")) return d.category === filter.slice(4);
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

function rowHtml() {
  return `
    <div class="cell-name"><span class="badge"></span><div class="name-wrap"><div class="fname"></div><div class="fhost"></div></div></div>
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

export function renderTable(tbody, rows, selected, emptyMsg) {
  const existing = new Map([...tbody.querySelectorAll(".row")].map((r) => [r.dataset.id, r]));
  if (!rows.length) {
    tbody.innerHTML = `<div class="empty">${emptyMsg}</div>`;
    return;
  }
  tbody.querySelector(".empty")?.remove();
  let prev = null;
  for (const d of rows) {
    let el = existing.get(d.id);
    if (!el) {
      el = document.createElement("div");
      el.className = "grid-row row";
      el.dataset.id = d.id;
      el.innerHTML = rowHtml();
    }
    existing.delete(d.id);
    const showSpeed = d.status === "downloading";
    el.classList.toggle("sel", selected.has(d.id));
    set(el, ".badge", d.badge);
    set(el, ".fname", d.filename || d.title || d.url);
    el.querySelector(".fname").title = d.filename;
    set(el, ".fhost", d.host);
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
    // keep DOM order in sync
    const want = prev ? prev.nextSibling : tbody.firstChild;
    if (want !== el) tbody.insertBefore(el, want);
    prev = el;
  }
  for (const el of existing.values()) el.remove();
}

export { esc };
