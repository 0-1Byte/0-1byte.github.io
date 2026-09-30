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
      const response = await fetch(
        `https://v3.sg.media-imdb.com/suggestion/x/${encodeURIComponent(title)}.json`
      );
      if (!response.ok) return;
      const data = await response.json();
      const wanted = normalize(title);
      const match = (data.d || []).find(item =>
        normalize(item.l) === wanted && item.i && item.i.imageUrl
      );
      if (match) image.src = match.i.imageUrl;
    } catch (error) {
      console.warn("Alternative documentary cover unavailable:", error);
    }
  }

  function render(docus) {
    grid.innerHTML = docus.map((docu, index) => {
      const title = text(docu.title);
      const details = [docu.year, docu.note].filter(Boolean).join(" · ");
      const image = buildCoverImg({
        cover: docu.cover,
        img: docu.img,
        alt: title,
        index,
        eagerCount: 4
      });
      const overlay = `<div class="docu-overlay" aria-label="${escape(`${title} 纪录片信息`)}">${details ? `<p><span>记录</span>${escape(details)}</p>` : ""}</div>`;
      const coverBlock = docu.url
        ? `<a class="cover-link" href="${escape(docu.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${escape(title)}"><div class="cover-wrap">${image}${overlay}<span class="external">↗</span></div></a>`
        : `<div class="cover-link"><div class="cover-wrap">${image}${overlay}</div></div>`;
      return `<article class="docu-card">${coverBlock}<div class="docu-info"><h2>${escape(title)}</h2></div></article>`;
    }).join("");
    bindCoverJpgFallback(grid);
    grid.querySelectorAll("img.cover").forEach(image => {
      image.addEventListener("error", () => {
        loadAlternativeCover(image, image.alt);
      });
    });
    count.textContent = `${docus.length} ${docus.length === 1 ? "documentary" : "documentaries"}`;
    empty.hidden = docus.length !== 0;
  }

  async function loadDocus() {
    const url = `${base}docus.json?v=2`;
    setCollectionLoading(error, "纪录片数据");
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
    render(result.data.filter(docu => docu && docu.title && docu.cover));
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
