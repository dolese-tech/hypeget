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

  // Download buttons: link straight to the files of the latest GitHub release.
  // No release yet: say so instead of sending people to an empty page.
  const assetLinks = document.querySelectorAll("[data-asset]");
  if (assetLinks.length) {
    const PATTERNS = { setup: /^HyperGet-Setup-.*\.exe$/i, portable: /^HyperGet-portable-.*\.zip$/i };
    const notice = document.getElementById("releaseNotice");
    const unavailable = () => {
      assetLinks.forEach((a) => {
        a.classList.add("is-disabled");
        a.setAttribute("aria-disabled", "true");
        a.removeAttribute("href");
      });
      if (notice) notice.hidden = false;
    };
    fetch("https://api.github.com/repos/dolese-tech/hypeget/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
      .then((r) => {
        if (r.status === 404) return null;            // no release published yet
        if (!r.ok) throw new Error(String(r.status));  // rate limit etc.: keep the fallback links
        return r.json();
      })
      .then((rel) => {
        if (!rel) return unavailable();
        let found = 0;
        assetLinks.forEach((a) => {
          const asset = (rel.assets || []).find((x) => PATTERNS[a.dataset.asset]?.test(x.name));
          if (!asset) return;
          a.href = asset.browser_download_url;
          found++;
          document.querySelectorAll(`[data-file="${a.dataset.asset}"]`).forEach((el) => { el.textContent = asset.name; });
        });
        if (!found) return unavailable();
        const v = String(rel.tag_name || "").replace(/^v/, "");
        if (v) document.querySelectorAll("[data-version]").forEach((el) => { el.textContent = v; });
      })
      .catch(() => { /* GitHub unreachable: the buttons keep linking to the releases page */ });
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
