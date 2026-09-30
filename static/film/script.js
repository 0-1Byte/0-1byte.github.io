(() => {
  "use strict";
  const base = "/film/";
  const grid = document.getElementById("film-grid");
  const count = document.getElementById("film-count");
  const empty = document.getElementById("empty");
  const error = document.getElementById("error");
  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[char]));
  const normalize = value => text(value).toLocaleLowerCase().replace(/\s+/g, " ").trim();

  // 交给 /covers.js 生成 srcset/sizes 与首屏优先级（档位与 tools/optimize_covers.py 一致）
  window.COVER_OPT = {
    widths: [240, 320, 480],
    sizes: "(max-width: 600px) 45vw, (max-width: 850px) 31vw, 235px",
    assetDir: "covers/opt"
  };

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
      console.warn("Alternative film cover unavailable:", loadError);
    }
  }

  function render(films) {
    grid.innerHTML = films.map((film, index) => {
      const title = text(film.title);
      const details = [film.year, film.note].filter(Boolean).join(" · ");
      const image = buildCoverImg({
        cover: film.cover,
        img: film.img,
        alt: title,
        index,
        eagerCount: 4
      });
      const overlay = `<div class="film-overlay" aria-label="${escape(`${title} 电影信息`)}">${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = film.url
        ? `<a class="cover-link" href="${escape(film.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="film-card">${coverBlock}<div class="film-info"><h2>${escape(title)}</h2></div></article>`;
    }).join("");
    bindCoverJpgFallback(grid);
    grid.querySelectorAll("img.cover").forEach(image => {
      image.addEventListener("error", () => loadAlternativeCover(image, image.alt));
    });
    count.textContent = `${films.length} ${films.length === 1 ? "film" : "films"}`;
    empty.hidden = films.length !== 0;
  }

  async function loadFilms() {
    const url = `${base}films.json?v=2`;
    setCollectionLoading(error, "电影数据");
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
        url, kind: "data",
        reason: "顶层不是 JSON 数组",
        detail: `实际类型：${result.data === null ? "null" : typeof result.data}`
      });
      return;
    }

    error.hidden = true;
    render(result.data.filter(film => film && film.title && film.cover));
  }

  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) document.documentElement.dataset.theme = event.newValue;
  });
  /* 页脚年份：拿不到元素就跳过。
     这里刻意保留非空判断 —— 同一个脚本里若有一句「拿到元素就直接用」
     并在 null 上抛错，会把后面那句加载调用一起带走，整页数据变空。
     那种情况真实发生过（主题切换按钮被移除时）。 */
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
  loadFilms();
})();
