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

  function render(books) {
    grid.innerHTML = books.map(book => {
      const title = text(book.title);
      const author = text(book.author);
      const cover = asset(book.cover);
      const details = [book.status, book.note].filter(Boolean).join(" · ");
      const image = `<img class="cover" src="${escape(cover)}" alt="${escape(title)}" loading="lazy">`;
      const overlay = `<div class="book-overlay" aria-label="${escape(`${title} 书籍信息`)}"><p><span>作者</span>${escape(author)}</p>${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = book.url
        ? `<a class="cover-link" href="${escape(book.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="book-card">${coverBlock}<div class="book-info"><h2>${escape(title)}</h2>${author ? `<p>${escape(author)}</p>` : ""}</div></article>`;
    }).join("");
    count.textContent = `${books.length} ${books.length === 1 ? "book" : "books"}`;
    empty.hidden = books.length !== 0;
  }

  async function loadBooks() {
    try {
      const response = await fetch(`${base}books.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("books.json must contain an array");
      render(data.filter(book => book && book.title && book.cover));
    } catch (loadError) {
      console.error("Book library:", loadError);
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
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });
  document.getElementById("year").textContent = new Date().getFullYear();
  loadBooks();
})();
