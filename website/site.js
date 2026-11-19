// Mobile menu + "Copy download link" for phone visitors.
(() => {
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
