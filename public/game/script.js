(() => {
  "use strict";

  const base = "/game/";
  const grid = document.getElementById("game-grid");
  const count = document.getElementById("game-count");
  const empty = document.getElementById("empty");
  const error = document.getElementById("error");
  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));

  function render(games) {
    grid.innerHTML = games.map((game, index) => {
      const title = text(game.title);
      const details = [
        game.platform && ["平台", game.platform],
        game.year && ["年份", game.year],
        game.note && ["记录", game.note]
      ].filter(Boolean).map(([label, value]) =>
        `<p><span>${escape(label)}</span>${escape(value)}</p>`
      ).join("");
      const art = game.cover
        ? buildCoverImg({ cover: game.cover, img: game.img, alt: title, index, eagerCount: 4 })
        : `<div class="game-placeholder" aria-hidden="true"><span>GAME</span></div>`;
      const cover = `<div class="cover-wrap">${art}${details ? `<div class="game-overlay" aria-label="${escape(`${title} 游戏信息`)}">${details}</div>` : ""}</div>`;
      const coverBlock = game.url
        ? `<a class="cover-link" href="${escape(game.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}">${cover}<span class="external" aria-hidden="true">↗</span></a>`
        : `<div class="cover-link">${cover}</div>`;
      return `<article class="game-card">${coverBlock}<div class="game-info"><h2>${escape(title)}</h2></div></article>`;
    }).join("");

    bindCoverJpgFallback(grid);
    count.textContent = `${games.length} ${games.length === 1 ? "game" : "games"}`;
    empty.hidden = games.length !== 0;
  }

  async function loadGames() {
    const url = `${base}games.json?v=1`;
    setCollectionLoading(error, "游戏数据");
    const result = await fetchCollectionJson(url);

    if (!result.ok) {
      count.textContent = "";
      empty.hidden = true;
      grid.innerHTML = "";
      showCollectionError(error, result);
      return;
    }

    if (!Array.isArray(result.data)) {
      showCollectionError(error, {
        url,
        kind: "data",
        reason: "顶层不是 JSON 数组",
        detail: `实际类型：${result.data === null ? "null" : typeof result.data}`
      });
      return;
    }

    error.hidden = true;
    render(result.data.filter(game => game && game.title));
  }

  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });

  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
  loadGames();
})();
