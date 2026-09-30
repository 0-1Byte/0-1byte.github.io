(() => {
  "use strict";

  const base = "/book/";
  const grid = document.getElementById("book-grid");
  const count = document.getElementById("book-count");
  const empty = document.getElementById("empty");
  const error = document.getElementById("error");
  const themeToggle = document.getElementById("theme-toggle");

  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
  const asset = path => !path ? "" : (/^(https?:)?\/\//.test(path) || path.startsWith("/") ? path : base + path.replace(/^\.?\//, ""));

  // 交给 /covers.js 生成 srcset/sizes 与首屏优先级（档位与 tools/optimize_covers.py 一致）
  window.COVER_OPT = {
    widths: [240, 320, 480],
    sizes: "(max-width: 600px) 45vw, (max-width: 850px) 31vw, 235px",
    assetDir: "covers/opt"
  };

  function addCoverFallback(image, title) {
    if (image.dataset.fallbackTried) return;
    image.dataset.fallbackTried = "true";
    const fallback = image.dataset.fallback;
    if (fallback) image.src = fallback;
    else image.alt = `${title}（封面加载失败）`;
  }

  function render(books) {
    grid.innerHTML = books.map((book, index) => {
      const title = text(book.title);
      const author = text(book.author);
      const details = [book.status, book.note].filter(Boolean).join(" · ");
      // fallbackCover 是"联网找替代封面"用的，与本地 JPG 兜底互不冲突
      const extraAttrs = book.fallbackCover
        ? { "data-fallback": resolveCoverAsset(book.fallbackCover) }
        : null;
      const image = buildCoverImg({
        cover: book.cover,
        img: book.img,
        alt: title,
        index,
        eagerCount: 4,
        extraAttrs
      });
      const overlay = `<div class="book-overlay" aria-label="${escape(`${title} 书籍信息`)}"><p><span>作者</span>${escape(author)}</p>${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = book.url
        ? `<a class="cover-link" href="${escape(book.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="book-card">${coverBlock}<div class="book-info"><h2>${escape(title)}</h2>${author ? `<p>${escape(author)}</p>` : ""}</div></article>`;
    }).join("");
    bindCoverJpgFallback(grid);
    grid.querySelectorAll("img.cover").forEach(image => {
      image.addEventListener("error", () => addCoverFallback(image, image.alt));
    });
    count.textContent = `${books.length} ${books.length === 1 ? "book" : "books"}`;
    empty.hidden = books.length !== 0;
  }

  async function loadBooks() {
    const url = `${base}books.json?v=2`;
    setCollectionLoading(error, "书籍数据");
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
    render(result.data.filter(book => book && book.title && book.cover));
  }

  themeToggle.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("pref-theme", theme);
  });
  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });
  document.getElementById("year").textContent = new Date().getFullYear();
  loadBooks();
})();
