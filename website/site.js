// Mobile menu, "Copy download link" for phone visitors, and store links.
(() => {
  // Paste the store IDs here once the Chrome Web Store and Edge Add-ons approve the
  // extension (see docs/STORE_UPLOAD.md). Until then the buttons lead to manual setup.
  const STORE = { chrome: "", edge: "" };
  const STORE_URL = {
    chrome: (id) => `https://chromewebstore.google.com/detail/${id}`,
    edge: (id) => `https://microsoftedge.microsoft.com/addons/detail/${id}`,
  };
  if (STORE.chrome || STORE.edge) {
    document.querySelectorAll("[data-store]").forEach((a) => {
      const id = STORE[a.dataset.store];
      if (id) a.href = STORE_URL[a.dataset.store](id);
      else a.hidden = true;
    });
    document.querySelectorAll("[data-store-only]").forEach((el) => { el.hidden = false; });
    document.querySelectorAll("[data-manual-only]").forEach((el) => { el.hidden = true; });
  }

  const nav = document.getElementById("nav");
  const btn = document.getElementById("menuBtn");
  if (nav && btn) {
    btn.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", String(open));
      btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    });
    nav.querySelectorAll(".nav-links a").forEach((a) =>
      a.addEventListener("click", () => {
        nav.classList.remove("open");
        btn.setAttribute("aria-expanded", "false");
      }));
  }

  function toast(text) {
    const t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("role", "status");
    t.textContent = text;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
  }

  const copy = document.getElementById("copyLink");
  if (copy) {
    copy.addEventListener("click", async () => {
      const url = new URL("/download", location.href).href;
      try {
        await navigator.clipboard.writeText(url);
        toast("Link copied. Open it on your Windows PC.");
      } catch {
        toast(url);
      }
    });
  }
})();
