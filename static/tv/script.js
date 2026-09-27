(() => {
  "use strict";
  const base = "/tv/";
  const grid = document.getElementById("tv-grid");
  const count = document.getElementById("tv-count");
  const empty = document.getElementById("empty");
  const error = document.getElementById("error");
  const themeToggle = document.getElementById("theme-toggle");
  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char]));
  const asset = path => !path ? "" : (/^(https?:)?\/\//.test(path) || path.startsWith("/") ? path : base + path.replace(/^\.?\//, ""));
  const normalize = value => text(value).toLocaleLowerCase().replace(/\s+/g, " ").trim();

  async function loadAlternativeCover(image, title) {
    if (image.dataset.fallbackTried) return;
    image.dataset.fallbackTried = "true";
    try {
      const response = await fetch(`https://v3.sg.media-imdb.com/suggestion/x/${encodeURIComponent(title)}.json`);
      if (!response.ok) return;
      const data = await response.json();
      const wanted = normalize(title);
      const match = (data.d || []).find(item =>
        normalize(item.l) === wanted && item.i && item.i.imageUrl
      );
      if (match) image.src = match.i.imageUrl;
    } catch (loadError) {
      console.warn("Alternative TV cover unavailable:", loadError);
    }
  }

  function render(shows) {
    grid.innerHTML = shows.map(show => {
      const title = text(show.title);
      const cover = asset(show.cover);
      const details = [show.year, show.note].filter(Boolean).join(" · ");
      const image = `<img class="cover" src="${escape(cover)}" alt="${escape(title)}" loading="eager" decoding="async">`;
      const overlay = `<div class="tv-overlay" aria-label="${escape(`${title} 剧集信息`)}">${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = show.url
        ? `<a class="cover-link" href="${escape(show.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="tv-card">${coverBlock}<div class="tv-info"><h2>${escape(title)}</h2></div></article>`;
    }).join("");
    grid.querySelectorAll("img.cover").forEach(image => {
      image.addEventListener("error", () => loadAlternativeCover(image, image.alt));
    });
    count.textContent = `${shows.length} ${shows.length === 1 ? "show" : "shows"}`;
    empty.hidden = shows.length !== 0;
  }

  async function loadShows() {
    try {
      const response = await fetch(`${base}tvs.json?v=${Date.now()}`, { cache:"no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("tvs.json must contain an array");
      render(data.filter(show => show && show.title && show.cover));
    } catch (loadError) {
      console.error("TV library:", loadError);
      count.textContent = "";
      error.hidden = false;
    }
  }

  themeToggle.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("pref-theme", theme);
  });
  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) document.documentElement.dataset.theme = event.newValue;
  });
  document.getElementById("year").textContent = new Date().getFullYear();
  loadShows();
})();
