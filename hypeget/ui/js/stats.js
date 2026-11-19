// Statistics page (Pro): shown in place of the download list.
import { api } from "./api.js";
import { bytes, esc, speed } from "./format.js";

const TYPE_COLORS = { Video: "var(--purple)", Programs: "var(--blue)", Compressed: "var(--orange)",
  Music: "var(--green)", Documents: "var(--slate)", Other: "var(--teal)" };
const HOST_COLORS = ["var(--red)", "var(--orange)", "var(--green)", "var(--blue)", "var(--purple)", "var(--teal)"];
let period = "week";

function duration(sec) {
  sec = Math.round(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

function donut(types, total) {
  const r = 52, cx = 70, cy = 70;
  let acc = 0, arcs = "";
  for (const [name, b] of types) {
    const p = b / total;
    if (p <= 0) continue;
    if (p >= 0.9999) { arcs += `<circle cx="${cx}" cy="${cy}" r="${r}" stroke="${TYPE_COLORS[name] || "var(--slate)"}" stroke-width="20" fill="none"/>`; break; }
    const a0 = acc * 2 * Math.PI, a1 = (acc + p) * 2 * Math.PI;
    acc += p;
    const x0 = cx + r * Math.sin(a0), y0 = cy - r * Math.cos(a0), x1 = cx + r * Math.sin(a1), y1 = cy - r * Math.cos(a1);
    arcs += `<path d="M${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${p > 0.5 ? 1 : 0} 1 ${x1.toFixed(1)},${y1.toFixed(1)}" stroke="${TYPE_COLORS[name] || "var(--slate)"}" stroke-width="20" fill="none"/>`;
  }
  const [num, unit] = bytes(total, 1).split(" ");
  return `<div style="display:flex;gap:18px;align-items:center"><svg width="140" height="140" viewBox="0 0 140 140" style="flex:none">${arcs}
    <text x="70" y="68" text-anchor="middle" font-size="18" font-weight="700" fill="var(--text)">${num}</text>
    <text x="70" y="85" text-anchor="middle" font-size="11" fill="var(--text-3)">${unit} in total</text></svg>
    <div style="font-size:12.5px;display:grid;gap:6px">${types.slice(0, 6).map(([n, b]) =>
      `<span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${TYPE_COLORS[n] || "var(--slate)"};margin-right:7px"></i>${esc(n)} <b style="margin-left:4px">${Math.round(b / total * 100)}%</b></span>`).join("")}</div></div>`;
}

function render(el, s) {
  const maxBar = Math.max(1, ...s.bars.map((b) => b.bytes));
  const many = s.bars.length > 12;
  const bars = `<div class="bars${many ? " many" : ""}">${s.bars.map((b, i) => `
    <div class="b${i === s.bars.length - 1 ? " now" : ""}" title="${esc(b.label)}: ${bytes(b.bytes)}"><em>${b.bytes ? bytes(b.bytes, 1) : ""}</em>
      <i style="height:${(b.bytes / maxBar * 82).toFixed(1)}%"></i><span>${esc(b.label)}</span></div>`).join("")}</div>`;
  const typesTotal = s.types.reduce((a, [, b]) => a + b, 0);
  const hostMax = Math.max(1, ...s.hosts.map(([, b]) => b));
  const hostRows = s.hosts.length
    ? s.hosts.map(([h, b], i) => `<div class="hbar"><span title="${esc(h)}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(h)}</span><div class="bar"><i style="width:${(b / hostMax * 100).toFixed(1)}%;background:${HOST_COLORS[i]}"></i></div><span class="n">${bytes(b, 1)}</span></div>`).join("")
    : `<div class="empty-chart">Nothing downloaded yet.</div>`;
  const hMax = Math.max(1, ...s.hours);
  const best = s.hours.indexOf(Math.max(...s.hours));
  const hours = `<div class="hours">${s.hours.map((v, h) =>
    `<i title="${String(h).padStart(2, "0")}:00 · ${v ? speed(v) : "no data"}" style="background:color-mix(in srgb,var(--blue) ${v ? Math.round(20 + v / hMax * 80) : 0}%,var(--track))"></i>`).join("")}</div>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-3);margin-top:6px"><span>00:00</span><span>12:00</span><span>23:00</span></div>
    ${s.hours.some((v) => v) ? `<div class="callout" style="margin-top:12px">Your downloads are fastest around <b>${String(best).padStart(2, "0")}:00</b>. Big files? Use the <b>Scheduler</b> to run them then.</div>` : ""}`;
  const word = { week: "this week", month: "last 30 days", year: "last 12 months" }[s.period];
  const change = s.change == null ? `<div class="d n">${word}</div>`
    : `<div class="d${s.change < 0 ? " n" : ""}">${s.change >= 0 ? "▲" : "▼"} ${Math.abs(Math.round(s.change * 100))}% vs the period before</div>`;
  el.innerHTML = `
    <div class="kpis">
      <div class="card kpi"><div class="k">Downloaded ${word}</div><div class="v">${bytes(s.bytes, 1)}</div>${change}</div>
      <div class="card kpi"><div class="k">Files finished</div><div class="v">${s.files}</div><div class="d n">${s.failed ? `${s.failed} failed` : "none failed"}</div></div>
      <div class="card kpi"><div class="k">Average speed</div><div class="v">${s.avg_speed ? speed(s.avg_speed) : "—"}</div><div class="d n">while downloading</div></div>
      <div class="card kpi"><div class="k">Time downloading</div><div class="v">${duration(s.active_seconds)}</div><div class="d n">${word}</div></div>
    </div>
    <div class="two">
      <div class="card panel"><h4>Downloaded per ${s.period === "year" ? "month" : "day"} <div class="tabs">
        ${["week", "month", "year"].map((p) => `<span data-period="${p}" class="${p === s.period ? "on" : ""}">${p[0].toUpperCase() + p.slice(1)}</span>`).join("")}</div></h4>${bars}</div>
      <div class="card panel"><h4>By type <span>all time</span></h4>${typesTotal ? donut(s.types, typesTotal) : `<div class="empty-chart">Nothing downloaded yet.</div>`}</div>
    </div>
    <div class="two">
      <div class="card panel"><h4>Top sites <span>all time</span></h4>${hostRows}</div>
      <div class="card panel"><h4>Speed by hour <span>what you usually get</span></h4>${hours}</div>
    </div>`;
  el.querySelectorAll("[data-period]").forEach((t) => t.onclick = () => { period = t.dataset.period; loadStats(el); });
}

export async function loadStats(el) {
  try {
    render(el, await api.stats(period));
  } catch (e) {
    el.innerHTML = `<div class="msg error">${esc(e.message)}</div>`;
  }
}
