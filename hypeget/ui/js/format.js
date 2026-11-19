export function bytes(n, digits) {
  if (n == null || isNaN(n)) return "—";
  if (n < 1024) return `${Math.round(n)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n, i = -1;
  do { v /= 1024; i++; } while (v >= 1024 && i < units.length - 1);
  const d = digits ?? (i >= 2 || v < 10 ? 1 : 0);
  return `${v.toFixed(d)} ${units[i]}`;
}

export const speed = (bps) => (bps > 0 ? `${bytes(bps, 1)}/s` : "—");

export function eta(sec) {
  if (sec == null || !isFinite(sec)) return "—";
  sec = Math.max(1, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

export function added(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return d.toLocaleDateString(undefined, { weekday: "short" });
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const pct = (p) => `${Math.floor((p || 0) * 100)}%`;

export function statusLabel(d) {
  switch (d.status) {
    case "downloading": return `${pct(d.progress)} · Downloading`;
    case "paused": return d.progress > 0 ? `${pct(d.progress)} · Paused` : "Paused";
    case "complete": return "Complete";
    case "error": return `Error · ${d.error || "Failed"}`;
    case "queued": return "Queued";
    case "connecting": return "Connecting…";
    case "merging": return "Merging…";
    default: return d.status;
  }
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const isUrl = (s) => /^https?:\/\/\S+$/i.test((s || "").trim());
