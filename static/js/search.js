(async function () {
  const input = document.getElementById("site-search-input");
  const box = document.getElementById("site-search-results");
  if (!input || !box) return;

  let items = [];
  try {
    const r = await fetch("/static/search-index.json", { cache: "no-store" });
    items = await r.json();
  } catch {
    return;
  }

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (m) => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
    }[m]));
  }

  function score(it, q) {
    const hay = `${it.title} ${it.description} ${it.tags}`.toLowerCase();
    if (hay.includes(q)) return 3;
    const parts = q.split(/\s+/).filter(Boolean);
    let s = 0;
    for (const p of parts) if (hay.includes(p)) s += 1;
    return s;
  }

  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = input.value.trim().toLowerCase();
      if (q.length < 2) { box.innerHTML = ""; return; }

      const ranked = items
        .map(it => ({ it, s: score(it, q) }))
        .filter(x => x.s > 0)
        .sort((a,b) => b.s - a.s)
        .slice(0, 10)
        .map(x => x.it);

      box.innerHTML = ranked.map(it => `
        <div class="sr-item">
          <a class="sr-title" href="${esc(it.url)}">${esc(it.title)}</a>
          <div class="sr-desc">${esc(it.description)}</div>
        </div>
      `).join("");
    }, 120);
  });
})();
