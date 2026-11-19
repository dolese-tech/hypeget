// Floating "Download this video" button over <video> players, with a quality menu.
(() => {
  if (window.__hypergetInjected) return;
  if (typeof hypergetRestricted === "function" && hypergetRestricted(location.href)) return;
  window.__hypergetInjected = true;

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483647;top:0;left:0;width:0;height:0;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      * { box-sizing: border-box; font-family: "Inter", "Segoe UI", system-ui, sans-serif; }
      .btn { position: fixed; display: none; align-items: center; gap: 7px; height: 30px; padding: 0 12px 0 9px;
        border: 0; border-radius: 7px; background: #2563eb; color: #fff; font-size: 12.5px; font-weight: 600;
        cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.28); opacity: .94; }
      .btn:hover { opacity: 1; background: #1d4ed8; }
      .btn svg { width: 15px; height: 15px; }
      .menu { position: fixed; display: none; min-width: 250px; max-width: 340px; background: #fff; color: #0f172a;
        border-radius: 10px; box-shadow: 0 12px 34px rgba(15,23,42,.3); padding: 6px; font-size: 13px; }
      .menu .head { padding: 7px 9px 8px; font-size: 11.5px; color: #64748b; border-bottom: 1px solid #e2e8f0; margin-bottom: 4px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .menu .head b { color: #0f172a; font-weight: 600; font-size: 12.5px; display: block; margin-bottom: 2px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .opt { display: grid; grid-template-columns: 64px 1fr auto; gap: 8px; align-items: center; width: 100%; border: 0;
        background: none; padding: 8px 9px; border-radius: 6px; cursor: pointer; text-align: left; font-size: 13px; color: inherit; }
      .opt:hover { background: #eff6ff; }
      .opt .q { font-weight: 600; } .opt .d { color: #64748b; font-size: 11.5px; } .opt .s { color: #334155; font-size: 12px; }
      .note { padding: 10px; color: #334155; line-height: 1.45; font-size: 12.5px; }
      .note.err { color: #dc2626; }
      .spin { width: 13px; height: 13px; border: 2px solid #e2e8f0; border-top-color: #2563eb; border-radius: 50%;
        display: inline-block; vertical-align: -2px; margin-right: 8px; animation: s .7s linear infinite; }
      @keyframes s { to { transform: rotate(360deg); } }
    </style>
    <button class="btn" part="btn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/></svg>Download this video</button>
    <div class="menu"></div>`;
  const btn = root.querySelector(".btn");
  const menu = root.querySelector(".menu");
  let current = null, hideTimer = null, menuOpen = false;

  const mount = () => { if (!host.isConnected) (document.body || document.documentElement).appendChild(host); };

  function bigEnough(v) {
    const r = v.getBoundingClientRect();
    return r.width >= 220 && r.height >= 120 && r.bottom > 0 && r.top < innerHeight;
  }

  function place() {
    if (!current) return;
    const r = current.getBoundingClientRect();
    if (!bigEnough(current)) { if (!menuOpen) hide(); return; }
    const top = Math.max(8, r.top + 10);
    btn.style.top = `${top}px`;
    btn.style.left = `${Math.min(innerWidth - 190, r.right - 186)}px`;
    if (menuOpen) {
      menu.style.top = `${top + 36}px`;
      menu.style.left = `${Math.max(8, Math.min(innerWidth - 350, r.right - 340 + 90))}px`;
    }
  }

  function show(v) {
    mount();
    current = v;
    clearTimeout(hideTimer);
    btn.style.display = "flex";
    place();
  }

  function hide() {
    if (menuOpen) return;
    btn.style.display = "none";
    current = null;
  }

  document.addEventListener("mouseover", (e) => {
    const v = e.target.closest?.("video") || [...document.querySelectorAll("video")].find((x) => {
      const r = x.getBoundingClientRect();
      return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    });
    if (v && bigEnough(v)) show(v);
    else if (current && !menuOpen) { clearTimeout(hideTimer); hideTimer = setTimeout(hide, 1800); }
  }, { passive: true });
  addEventListener("scroll", place, { passive: true, capture: true });
  addEventListener("resize", place, { passive: true });
  btn.addEventListener("mouseenter", () => clearTimeout(hideTimer));

  btn.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); openPicker(); });
  document.addEventListener("mousedown", (e) => {
    if (menuOpen && !e.composedPath().includes(host)) closeMenu();
  }, true);

  function closeMenu() { menuOpen = false; menu.style.display = "none"; }

  const fmtSize = (n) => !n ? "" : n > 1024 ** 3 ? `≈ ${(n / 1024 ** 3).toFixed(1)} GB` : `≈ ${Math.round(n / 1024 ** 2)} MB`;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  async function openPicker() {
    mount();
    if (!current) {
      const v = [...document.querySelectorAll("video")].find(bigEnough);
      if (v) show(v);
    }
    menuOpen = true;
    menu.style.display = "block";
    if (!current) { menu.style.top = "16px"; menu.style.left = `${innerWidth - 360}px`; }
    place();
    menu.innerHTML = `<div class="note"><span class="spin"></span>Finding qualities…</div>`;
    const src = current && (current.currentSrc || current.src);
    let res;
    try {
      res = await chrome.runtime.sendMessage({ type: "videoOptions", pageUrl: location.href, pageTitle: document.title.trim().slice(0, 120), src: src && !src.startsWith("blob:") ? src : "" });
    } catch (e) {
      res = { ok: false, error: "Extension was updated — reload this page." };
    }
    if (!menuOpen) return;
    if (!res?.ok) {
      menu.innerHTML = `<div class="note err">${esc(res?.error || "Something went wrong")}</div>`;
      return;
    }
    const { info, source } = res;
    menu.innerHTML = `<div class="head"><b>${esc(info.title)}</b>Choose a quality</div>` +
      info.options.map((o, i) => `<button class="opt" data-i="${i}"><span class="q">${esc(o.label)}</span><span class="d">${esc(o.detail || "")}</span><span class="s">${fmtSize(o.est_size)}</span></button>`).join("");
    menu.querySelectorAll(".opt").forEach((b) => b.onclick = async () => {
      const option = info.options[+b.dataset.i];
      menu.innerHTML = `<div class="note"><span class="spin"></span>Sending to HyperGet…</div>`;
      const r = await chrome.runtime.sendMessage({ type: "download", source, info, option });
      menu.innerHTML = r?.ok
        ? `<div class="note">✓ Added to HyperGet (${esc(option.label)}).</div>`
        : `<div class="note err">${esc(r?.error || "Failed")}</div>`;
      setTimeout(() => { closeMenu(); hide(); }, 1600);
    });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "openPicker" && window === window.top) openPicker();
  });
})();
