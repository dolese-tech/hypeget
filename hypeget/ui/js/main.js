import { api } from "./api.js";
import { renderDetails } from "./details.js";
import * as D from "./dialogs.js";
import { bytes, isUrl, speed } from "./format.js";
import { filterRows, renderTable, sortRows } from "./table.js";

const $ = (s) => document.querySelector(s);
const ui = {
  state: null,
  filter: "all",
  query: "",
  sort: { key: null, dir: 1 },
  selected: new Set(),
  anchor: null,
  visible: [],
  showDetails: true,
};

try {
  const saved = JSON.parse(localStorage.getItem("hg-ui") || "{}");
  if (saved.theme) document.documentElement.dataset.theme = saved.theme;
  if (saved.showDetails === false) ui.showDetails = false;
} catch { /* storage unavailable */ }
function persistUi() {
  try {
    localStorage.setItem("hg-ui", JSON.stringify({ theme: document.documentElement.dataset.theme, showDetails: ui.showDetails }));
  } catch { /* ignore */ }
}

const SPEEDS = [[0, "Unlimited"], [256 * 1024, "256 KB/s"], [512 * 1024, "512 KB/s"], [1024 ** 2, "1.0 MB/s"],
  [2 * 1024 ** 2, "2.0 MB/s"], [5 * 1024 ** 2, "5.0 MB/s"], [10 * 1024 ** 2, "10 MB/s"], [25 * 1024 ** 2, "25 MB/s"]];

// ------------------------------------------------------------------ data
async function refresh() {
  try {
    ui.state = await api.state();
    render();
  } catch (e) {
    $("#sbScheduler").textContent = "Engine not responding";
  }
}

function selectedItems() {
  if (!ui.state) return [];
  return ui.state.downloads.filter((d) => ui.selected.has(d.id));
}

function render() {
  const s = ui.state;
  if (!s) return;
  const ids = new Set(s.downloads.map((d) => d.id));
  for (const id of [...ui.selected]) if (!ids.has(id)) ui.selected.delete(id);

  // sidebar counts
  const c = s.counts;
  const counts = { all: c.all, unfinished: c.unfinished, finished: c.finished, queues: c.queues, grabber: c.grabber, ...c.categories };
  document.querySelectorAll("[data-count]").forEach((el) => { el.textContent = counts[el.dataset.count] ?? 0; });

  // table
  ui.visible = sortRows(filterRows(s.downloads, ui.filter, ui.query), ui.sort);
  const empty = s.downloads.length
    ? "<b>Nothing here</b>No downloads match this view."
    : "<b>No downloads yet</b>Click Add URL or paste a link (Ctrl+V) to start.";
  renderTable($("#tbody"), ui.visible, ui.selected, empty);

  // details
  const det = $("#details");
  det.classList.toggle("hidden", !ui.showDetails);
  const sel = selectedItems();
  renderDetails(det, sel.length ? sel[sel.length - 1] : null);

  // status bar
  $("#sbActive").textContent = s.active;
  $("#sbSpeed").textContent = s.total_speed > 0 ? speed(s.total_speed) : "0 B/s";
  $("#sbQueue").textContent = s.waiting;
  $("#sbScheduler").textContent = s.scheduler;

  // speed rule + 'when all downloads finish'
  const rule = $("#sbRule");
  rule.classList.toggle("hidden", !s.speed_rule_active);
  if (s.speed_rule_active) rule.textContent = `Working-hours limit ${bytes(s.effective_speed_limit, 1)}/s`;
  document.querySelectorAll("[data-done]").forEach((k) => { k.textContent = k.dataset.done === s.when_done ? "✓" : ""; });
  const pend = s.pending_action, banner = $("#doneBanner");
  banner.classList.toggle("hidden", !pend);
  if (pend) {
    const what = { sleep: "Putting the computer to sleep", shutdown: "Shutting down the computer", exit: "Closing HyperGet" }[pend.action] || pend.action;
    $("#doneText").textContent = `All downloads finished. ${what} in ${pend.in} s…`;
  }

  // speed limit
  const lim = s.settings.speed_limit;
  const preset = SPEEDS.find(([v]) => v === lim);
  $("#speedLabel").textContent = preset ? preset[1] : `${bytes(lim, 1)}/s`;

  // toolbar enablement
  const any = sel.length > 0;
  setEnabled("resume", sel.some((d) => ["paused", "error", "queued"].includes(d.status)));
  setEnabled("pause", sel.some((d) => ["downloading", "connecting", "queued", "merging"].includes(d.status)));
  setEnabled("delete", any);
  $("#detailsCheck").textContent = ui.showDetails ? "✓" : "";
  $("#themeCheck").textContent = document.documentElement.dataset.theme === "dark" ? "✓" : "";
}

function setEnabled(act, on) {
  const b = document.querySelector(`.tool[data-act="${act}"]`);
  if (b) b.disabled = !on;
}

// ------------------------------------------------------------------ commands
async function forSelected(action, filter) {
  const items = selectedItems().filter(filter || (() => true));
  for (const d of items) await api.action(d.id, action).catch((e) => D.toast(e.message));
  refresh();
}

const commands = {
  add: () => D.addUrlDialog(isUrl(ui.query) ? ui.query.trim() : "", afterAdd),
  batch: () => D.batchDialog(refresh),
  resume: () => forSelected("resume", (d) => ["paused", "error", "queued"].includes(d.status)),
  pause: () => forSelected("pause"),
  redownload: () => forSelected("redownload"),
  stop: async () => { await api.stopAll(); refresh(); },
  startqueue: async () => { await api.startQueue(); refresh(); },
  delete: () => { const items = selectedItems(); if (items.length) D.deleteDialog(items, refresh); },
  scheduler: () => ui.state && D.schedulerDialog(ui.state.settings),
  queue: () => ui.state && D.queueDialog(ui.state),
  grabber: () => D.grabberDialog(refresh),
  options: () => ui.state && D.optionsDialog(ui.state),
  open: () => { const d = selectedItems().find((x) => x.status === "complete"); if (d) api.action(d.id, "open").catch((e) => D.toast(e.message)); },
  folder: () => { const d = selectedItems()[0]; if (d) api.action(d.id, "folder").catch((e) => D.toast(e.message)); },
  copy: async () => {
    const d = selectedItems()[0];
    if (!d) return;
    try { await navigator.clipboard.writeText(d.url); D.toast("Link copied"); } catch { D.toast(d.url, 5000); }
  },
  clearfinished: async () => {
    for (const d of ui.state.downloads.filter((x) => x.status === "complete")) await api.remove(d.id, false);
    refresh();
  },
  details: () => { ui.showDetails = !ui.showDetails; persistUi(); render(); },
  theme: () => {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    persistUi(); render();
  },
  extension: () => D.extensionDialog(),
  about: () => api.state().then(() => D.aboutDialog("0.1.0")),
  sites: () => D.sitesDialog(!!ui.state?.features.sites),
  exit: () => window.pywebview?.api?.quit ? window.pywebview.api.quit() : window.close(),
};

function afterAdd() {
  $("#search").value = "";
  ui.query = "";
  refresh();
}

function run(cmd, arg) {
  closeMenus();
  if (cmd.startsWith("done:")) {
    const action = cmd.slice(5);
    api.whenDone(action).then(() => {
      if (action !== "nothing") D.toast({ sleep: "The computer will sleep when all downloads finish",
        shutdown: "The computer will shut down when all downloads finish", exit: "HyperGet will close when all downloads finish" }[action]);
      refresh();
    }).catch((e) => D.toast(e.message));
    return;
  }
  const f = arg !== undefined && cmd === "add" ? () => D.addUrlDialog(arg, afterAdd) : commands[cmd];
  if (f) Promise.resolve(f()).catch((e) => D.toast(e.message));
}

// ------------------------------------------------------------------ menus
function closeMenus() {
  document.querySelectorAll(".menu.open").forEach((m) => m.classList.remove("open"));
  document.querySelector(".ctx")?.remove();
}

document.querySelectorAll("#menubar > .menu").forEach((menu) => {
  const btn = menu.querySelector(":scope > button");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = menu.classList.contains("open");
    closeMenus();
    if (!open) { syncMenuState(menu); menu.classList.add("open"); }
  });
  btn.addEventListener("mouseenter", () => {
    if (document.querySelector("#menubar .menu.open") && !menu.classList.contains("open")) {
      closeMenus(); syncMenuState(menu); menu.classList.add("open");
    }
  });
});

function syncMenuState(root) {
  const sel = selectedItems();
  root.querySelectorAll("[data-need]").forEach((b) => {
    b.disabled = b.dataset.need === "complete" ? !sel.some((d) => d.status === "complete") : sel.length === 0;
  });
}

document.addEventListener("click", (e) => {
  const cmdBtn = e.target.closest("[data-cmd]");
  if (cmdBtn && !cmdBtn.disabled) { e.stopPropagation(); run(cmdBtn.dataset.cmd); return; }
  if (!e.target.closest(".menu")) closeMenus();
});

// speed limit dropdown
const speedDrop = $("#speedDrop");
speedDrop.innerHTML = SPEEDS.map(([v, l]) => `<button data-speed="${v}">${l}</button>`).join("") +
  `<hr><button data-speed="custom">Custom…</button>`;
$("#speedBtn").addEventListener("click", (e) => {
  e.stopPropagation();
  const m = $("#speedMenu"), open = m.classList.contains("open");
  closeMenus();
  if (!open) m.classList.add("open");
});
speedDrop.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-speed]");
  if (!b) return;
  e.stopPropagation();
  closeMenus();
  let v = b.dataset.speed;
  if (v === "custom") {
    const kb = prompt("Speed limit in KB/s (0 = unlimited)", Math.round((ui.state?.settings.speed_limit || 0) / 1024));
    if (kb === null) return;
    v = Math.max(0, parseInt(kb, 10) || 0) * 1024;
  }
  await api.speedLimit(+v);
  refresh();
});

// ------------------------------------------------------------------ toolbar & sidebar
document.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", (e) => {
  e.preventDefault();
  run(b.dataset.act === "stop" ? "stop" : b.dataset.act);
}));

$("#sidebar").addEventListener("click", (e) => {
  const item = e.target.closest(".nav-item");
  if (!item) return;
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("sel", n === item));
  ui.filter = item.dataset.filter;
  if (ui.filter === "grabber") run("grabber");
  render();
});

// sorting
$("#thead").addEventListener("click", (e) => {
  const h = e.target.closest("[data-sort]");
  if (!h) return;
  const key = h.dataset.sort;
  if (ui.sort.key === key) ui.sort.dir = ui.sort.dir > 0 ? -1 : (ui.sort.key = null, 1);
  else ui.sort = { key, dir: 1 };
  document.querySelectorAll("#thead .arrow").forEach((a) => a.remove());
  if (ui.sort.key) h.insertAdjacentHTML("beforeend", `<span class="arrow">${ui.sort.dir > 0 ? "▲" : "▼"}</span>`);
  render();
});

// ------------------------------------------------------------------ selection
const tbody = $("#tbody");
tbody.addEventListener("mousedown", (e) => {
  const row = e.target.closest(".row");
  if (!row) { if (e.button === 0) { ui.selected.clear(); render(); } return; }
  const id = row.dataset.id;
  if (e.button === 2 && ui.selected.has(id)) return;
  if (e.shiftKey && ui.anchor) {
    const ids = ui.visible.map((d) => d.id);
    const a = ids.indexOf(ui.anchor), b = ids.indexOf(id);
    ui.selected = new Set(ids.slice(Math.min(a, b), Math.max(a, b) + 1));
  } else if (e.ctrlKey || e.metaKey) {
    ui.selected.has(id) ? ui.selected.delete(id) : ui.selected.add(id);
    ui.anchor = id;
  } else {
    ui.selected = new Set([id]);
    ui.anchor = id;
  }
  render();
});
tbody.addEventListener("dblclick", (e) => {
  const row = e.target.closest(".row");
  if (!row) return;
  const d = ui.state.downloads.find((x) => x.id === row.dataset.id);
  if (!d) return;
  if (d.status === "complete") run("open");
  else if (["paused", "error"].includes(d.status)) run("resume");
});
tbody.addEventListener("contextmenu", (e) => {
  const row = e.target.closest(".row");
  if (!row) return;
  e.preventDefault();
  closeMenus();
  const sel = selectedItems();
  const done = sel.some((d) => d.status === "complete");
  const canResume = sel.some((d) => ["paused", "error", "queued"].includes(d.status));
  const canPause = sel.some((d) => ["downloading", "connecting", "queued", "merging"].includes(d.status));
  const m = document.createElement("div");
  m.className = "ctx dropdown show";
  m.innerHTML = `
    <button data-cmd="open" ${done ? "" : "disabled"}>Open</button>
    <button data-cmd="folder">Open folder</button><hr>
    <button data-cmd="resume" ${canResume ? "" : "disabled"}>Resume</button>
    <button data-cmd="pause" ${canPause ? "" : "disabled"}>Pause</button>
    <button data-cmd="redownload">Redownload</button><hr>
    <button data-cmd="copy">Copy link</button>
    <button data-cmd="delete">Delete…</button>`;
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = `${Math.min(e.clientX, innerWidth - r.width - 8)}px`;
  m.style.top = `${Math.min(e.clientY, innerHeight - r.height - 8)}px`;
});

// ------------------------------------------------------------------ search / paste
$("#search").addEventListener("input", (e) => { ui.query = e.target.value; render(); });
$("#searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  if (isUrl(ui.query)) run("add");
});
document.addEventListener("paste", (e) => {
  if (e.target.closest("input, textarea") || document.querySelector(".overlay")) return;
  const text = (e.clipboardData?.getData("text") || "").trim();
  const links = text.split(/\s+/).filter(isUrl);
  if (links.length === 1) D.addUrlDialog(links[0], afterAdd);
  else if (links.length > 1) api.addMany(links.map((url) => ({ url }))).then(() => { D.toast(`Added ${links.length} downloads`); refresh(); });
});

document.addEventListener("keydown", (e) => {
  if (document.querySelector(".overlay")) return;
  const inInput = e.target.closest("input, textarea");
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") { e.preventDefault(); run("add"); }
  else if (inInput) return;
  else if (e.key === "Delete") run("delete");
  else if (e.key === "Enter") run("open");
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
    e.preventDefault(); ui.selected = new Set(ui.visible.map((d) => d.id)); render();
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const ids = ui.visible.map((d) => d.id);
    let i = ids.indexOf(ui.anchor);
    i = Math.max(0, Math.min(ids.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)));
    if (ids[i]) { ui.selected = new Set([ids[i]]); ui.anchor = ids[i]; render(); }
  } else if (e.key === "Escape") closeMenus();
});

// ------------------------------------------------------------------ window controls
document.querySelectorAll("[data-win]").forEach((b) => b.addEventListener("click", () => {
  const w = window.pywebview?.api;
  if (!w) return;
  ({ min: () => w.minimize(), max: () => w.toggle_maximize(), close: () => w.close() })[b.dataset.win]();
}));
if (!window.pywebview && !navigator.userAgent.includes("pywebview")) {
  // Plain browser tab: the native window controls do nothing, hide them.
  window.addEventListener("pywebviewready", () => document.querySelector(".win-controls").style.display = "");
  document.querySelector(".win-controls").style.display = "none";
}

// The app (tray menu, a second HyperGet start) can run commands here, e.g. "add".
// "add" may carry a link (copied to the clipboard); don't stack dialogs over an open one.
window.hgCommand = (cmd, arg) => {
  if (!commands[cmd]) return;
  if (arg !== undefined && (!isUrl(arg) || document.querySelector(".overlay"))) return;
  run(cmd, arg);
};
$("#doneCancel").addEventListener("click", () => api.cancelWhenDone().then(refresh));

// ------------------------------------------------------------------ go
refresh();
setInterval(refresh, 500);
