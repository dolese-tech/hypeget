const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n) => !n ? "" : n > 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : n > 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
const send = (msg) => chrome.runtime.sendMessage(msg);

let tab;

function renderOptions(container, res) {
  if (!res?.ok) { container.innerHTML = `<div class="msg err">${esc(res?.error || "Failed")}</div>`; return; }
  const { info, source } = res;
  container.innerHTML = `<div class="sub" style="margin:6px 0 2px">${esc(info.title)}</div><div class="opts">${
    info.options.map((o, i) => `<button data-i="${i}" title="${esc(o.detail || "")}">${esc(o.label)}${o.est_size ? " · " + fmt(o.est_size) : ""}</button>`).join("")}</div>`;
  container.querySelectorAll("[data-i]").forEach((b) => b.onclick = async () => {
    const r = await send({ type: "download", source, info, option: info.options[+b.dataset.i] });
    container.innerHTML = r?.ok ? `<div class="msg">✓ Sent to HyperGet</div>` : `<div class="msg err">${esc(r?.error)}</div>`;
  });
}

async function init() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const st = await send({ type: "status" });
  const s = st.settings;
  $("#status").className = st.alive ? "on" : "off";
  $("#status").innerHTML = `<span class="dot"></span>${st.alive ? "Connected" : "App not running"}`;
  $("#intercept").checked = s.intercept;
  $("#minMB").value = s.minInterceptMB;
  $("#port").value = s.port;

  const { items } = await send({ type: "media", tabId: tab.id });
  if (items.length) {
    $("#list").innerHTML = items.map((m, i) => `
      <div class="item" data-i="${i}">
        <span class="badge">${m.kind === "hls" ? "HLS" : esc((m.name.split(".").pop() || "FILE").slice(0, 4).toUpperCase())}</span>
        <div style="min-width:0"><div class="name" title="${esc(m.url)}">${esc(m.name)}</div><div class="sub">${esc(new URL(m.url).hostname)}${m.size ? " · " + fmt(m.size) : ""}</div></div>
        <button class="dl">Download</button>
        <div class="opts-wrap" style="grid-column:1/-1"></div>
      </div>`).join("");
    $("#list").querySelectorAll(".item").forEach((el) => el.querySelector(".dl").onclick = async () => {
      const m = items[+el.dataset.i];
      const box = el.querySelector(".opts-wrap");
      box.innerHTML = `<div class="msg">Checking qualities…</div>`;
      renderOptions(box, await send({ type: "inspect", url: m.url, headers: m.headers, pageUrl: tab.url }));
    });
  }

  $("#pageVideo").onclick = async () => {
    $("#pageOpts").innerHTML = `<div class="msg">Finding qualities…</div>`;
    renderOptions($("#pageOpts"), await send({ type: "videoOptions", tabId: tab.id, pageUrl: tab.url, pageTitle: tab.title }));
  };

  const save = () => send({ type: "saveSettings", settings: {
    intercept: $("#intercept").checked,
    minInterceptMB: Math.max(0, +$("#minMB").value || 0),
    port: +$("#port").value || 52817,
  } });
  ["intercept", "minMB", "port"].forEach((id) => $("#" + id).addEventListener("change", save));
}

init();
