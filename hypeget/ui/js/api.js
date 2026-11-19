// Thin client for the local HyperGet API (same origin).
async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-HyperGet": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  state: () => call("GET", "/api/state"),
  inspect: (url) => call("POST", "/api/inspect", { url }),
  add: (item) => call("POST", "/api/downloads", item),
  addMany: (items) => call("POST", "/api/downloads", { items }),
  action: (id, action) => call("POST", `/api/downloads/${id}/${action}`),
  remove: (id, file) => call("DELETE", `/api/downloads/${id}${file ? "?file=1" : ""}`),
  stopAll: () => call("POST", "/api/actions/stop_all"),
  startQueue: () => call("POST", "/api/actions/start_queue"),
  speedLimit: (bps) => call("POST", "/api/actions/speed_limit", { bytes_per_sec: bps }),
  settings: (changes) => call("POST", "/api/settings", changes),
  whenDone: (action) => call("POST", "/api/actions/when_done", { action }),
  cancelWhenDone: () => call("POST", "/api/actions/cancel_when_done"),
  grab: (url) => call("POST", "/api/grab", { url }),
};
