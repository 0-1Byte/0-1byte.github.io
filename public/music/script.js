(() => {
  "use strict";

  const MUSIC_BASE = "/music/";
  const grid = document.getElementById("song-grid");
  const count = document.getElementById("song-count");
  const error = document.getElementById("error");
  const themeToggle = document.getElementById("theme-toggle");

  function safeText(value) {
    return String(value ?? "");
  }

  function escapeHtml(value) {
    return safeText(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[char]));
  }

  function resolveAsset(path) {
    if (!path) return "";
    if (/^(https?:)?\/\//.test(path) || path.startsWith("/")) return path;
    return MUSIC_BASE + path.replace(/^\.?\//, "");
  }

  function render(songs) {
    grid.innerHTML = songs.map(song => {
      const title = safeText(song.title);
      const artist = safeText(song.artist);
      const cover = resolveAsset(song.cover);
      const lyricist = safeText(song.lyricist) || "未找到词作者";
      const composer = safeText(song.composer) || "未找到曲作者";

      const image = `
        <img
          class="cover"
          src="${escapeHtml(cover)}"
          alt="${escapeHtml(title)}"
          loading="lazy"
        >
      `;

      const credits = `
        <div class="credit-overlay" aria-label="${escapeHtml(`${title} 词曲作者`)}">
          <p><span>词</span>${escapeHtml(lyricist)}</p>
          <p><span>曲</span>${escapeHtml(composer)}</p>
        </div>
      `;

      let coverBlock = `<div class="cover-link"><div class="cover-wrap">${image}${credits}</div></div>`;

      if (song.url) {
        coverBlock = `
          <a
            class="cover-link"
            href="${escapeHtml(song.url)}"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="打开 ${escapeHtml(title)}"
          >
            <div class="cover-wrap">
              ${image}
              ${credits}
              <span class="external" aria-hidden="true">↗</span>
            </div>
          </a>
        `;
      }

      return `
        <article class="song-card">
          ${coverBlock}
          <div class="song-info">
            <h2 class="title">${escapeHtml(title)}</h2>
            ${artist ? `<p class="artist">${escapeHtml(artist)}</p>` : ""}
          </div>
        </article>
      `;
    }).join("");

    count.textContent = `${songs.length} ${songs.length === 1 ? "song" : "songs"}`;
  }

  async function loadSongs() {
    try {
      const response = await fetch(`${MUSIC_BASE}songs.json?v=${Date.now()}`, {
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      if (!Array.isArray(data)) {
        throw new Error("songs.json must contain an array");
      }

      render(data.filter(song => song && song.title && song.cover));
    } catch (err) {
      console.error("Music library:", err);
      count.textContent = "";
      error.hidden = false;
    }
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("pref-theme", theme);
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === "dark" ? "light" : "dark");
  });

  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });

  document.getElementById("year").textContent = new Date().getFullYear();

  loadSongs();
})();
