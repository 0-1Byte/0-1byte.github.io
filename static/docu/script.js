(() => {
  "use strict";

  const base = "/docu/";
  const grid = document.getElementById("docu-grid");
  const count = document.getElementById("docu-count");
  const empty = document.getElementById("empty");
  const error = document.getElementById("error");
  const themeToggle = document.getElementById("theme-toggle");

  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
  const asset = path => !path ? "" : (/^(https?:)?\/\//.test(path) || path.startsWith("/") ? path : base + path.replace(/^\.?\//, ""));

  function render(docus) {
    grid.innerHTML = docus.map(docu => {
      const title = text(docu.title);
      const director = text(docu.director);
      const cover = asset(docu.cover);
      const details = [docu.year, docu.note].filter(Boolean).join(" · ");
      const image = `<img class="cover" src="${escape(cover)}" alt="${escape(title)}" loading="lazy">`;
      const overlay = `<div class="docu-overlay" aria-label="${escape(`${title} 纪录片信息`)}"><p><span>导演</span>${escape(director)}</p>${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = docu.url
        ? `<a class="cover-link" href="${escape(docu.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="docu-card">${coverBlock}<div class="docu-info"><h2>${escape(title)}</h2>${director ? `<p>${escape(director)}</p>` : ""}</div></article>`;
    }).join("");
    count.textContent = `${docus.length} ${docus.length === 1 ? "documentary" : "documentaries"}`;
    empty.hidden = docus.length !== 0;
  }

  async function loadDocus() {
    try {
      const response = await fetch(`${base}docus.json?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error("docus.json must contain an array");
      render(data.filter(docu => docu && docu.title && docu.cover));
    } catch (loadError) {
      console.error("Documentary library:", loadError);
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
  loadDocus();
})();
