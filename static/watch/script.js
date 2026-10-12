(() => {
  "use strict";

  const categories = [
    { name: "Film", url: "/film/films.json?v=2", base: "/film/" },
    { name: "TV", url: "/tv/tvs.json?v=2", base: "/tv/" },
    { name: "Docu", url: "/docu/docus.json?v=2", base: "/docu/" }
  ];
  const grid = document.getElementById("watch-grid");
  const count = document.getElementById("watch-count");
  const filters = document.getElementById("category-filters");
  const empty = document.getElementById("empty");
  const sourceErrors = document.getElementById("source-errors");
  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
  const normalize = value => text(value).toLocaleLowerCase().replace(/\s+/g, " ").trim();
  let activeCategory = "All";
  let itemsLoaded = false;

  window.COVER_OPT = {
    widths: [240, 320, 480],
    sizes: "(max-width: 600px) 45vw, (max-width: 850px) 31vw, 235px",
    assetDir: "covers/opt"
  };

  function renderFilters() {
    filters.innerHTML = ["All", ...categories.map(category => category.name)]
      .map(name => `<button class="category-filter" type="button" data-category="${escape(name)}" aria-pressed="${name === activeCategory}">${escape(name)}</button>`)
      .join("");
    filters.addEventListener("click", event => {
      const button = event.target.closest("button[data-category]");
      if (!button || !filters.contains(button)) return;
      activeCategory = button.dataset.category;
      filters.querySelectorAll("button[data-category]").forEach(item => {
        item.setAttribute("aria-pressed", String(item.dataset.category === activeCategory));
      });
      updateVisibleItems();
    });
  }

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
    } catch (error) {
      console.warn("Alternative watch cover unavailable:", error);
    }
  }

  function renderItems(items) {
    grid.innerHTML = items.map((entry, index) => {
      const { category, item, base } = entry;
      const title = text(item.title);
      const details = [item.year, item.note].filter(Boolean).join(" · ");
      const image = buildCoverImg({
        cover: item.cover,
        img: item.img,
        alt: title,
        index,
        eagerCount: 4,
        assetBase: base
      });
      const overlay = `<div class="watch-overlay" aria-label="${escape(`${title} ${category} information`)}">${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = item.url
        ? `<a class="cover-link" href="${escape(item.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="watch-card" data-category="${escape(category)}">${coverBlock}<div class="watch-info"><h2>${escape(title)}</h2></div></article>`;
    }).join("");
    bindCoverJpgFallback(grid);
    grid.querySelectorAll("img.cover").forEach(image => {
      image.addEventListener("error", () => loadAlternativeCover(image, image.alt));
    });
    itemsLoaded = true;
    updateVisibleItems();
  }

  function updateVisibleItems() {
    if (!itemsLoaded) {
      count.textContent = "Loading titles…";
      empty.hidden = true;
      return;
    }

    const cards = [...grid.querySelectorAll(".watch-card")];
    let visible = 0;
    cards.forEach(card => {
      card.hidden = activeCategory !== "All" && card.dataset.category !== activeCategory;
      if (!card.hidden) visible++;
    });
    count.textContent = `${visible} ${visible === 1 ? "title" : "titles"}`;
    empty.hidden = visible !== 0;
  }

  async function loadItems() {
    const results = await Promise.all(categories.map(async category => ({
      category,
      result: await fetchCollectionJson(category.url)
    })));
    const items = [];
    const failures = [];

    results.forEach(({ category, result }) => {
      if (!result.ok) {
        failures.push({ category, result });
        return;
      }
      if (!Array.isArray(result.data)) {
        failures.push({
          category,
          result: {
            url: category.url,
            kind: "data",
            reason: "顶层不是 JSON 数组",
            detail: `实际类型：${result.data === null ? "null" : typeof result.data}`
          }
        });
        return;
      }
      result.data
        .filter(item => item && item.title && item.cover)
        .forEach(item => items.push({ category: category.name, item, base: category.base }));
    });

    renderItems(items);
    failures.forEach(({ category, result }) => {
      const panel = document.createElement("div");
      panel.className = "collection-state";
      panel.setAttribute("aria-label", `${category.name} data error`);
      sourceErrors.appendChild(panel);
      showCollectionError(panel, result);
    });
    sourceErrors.hidden = failures.length === 0;
  }

  renderFilters();
  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
  loadItems();
})();
