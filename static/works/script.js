(() => {
  "use strict";

  /* 目录前缀由脚本自身 URL 推导（见 collection-common.js），
     这样根路径部署与 /sub/ 子目录部署都成立。
     注意两点：
       1. defer 脚本执行时 document.currentScript 为 null，只能反查 script 标签
       2. 用 getAttribute("src") 而不是 .src —— 后者依赖属性反射，取值更稳 */
  const selfScript = document.querySelector('script[src$="/works/script.js?v=2"]')
    || document.querySelector('script[src*="/works/script.js"]');
  const base = derivePageBase(selfScript && selfScript.getAttribute("src"));
  const DATA_VERSION = "2";        // works.json 有更新时改这个数字即可破缓存
  const grid = document.getElementById("works-grid");
  const count = document.getElementById("works-count");
  const range = document.getElementById("works-range");
  const toolbar = document.getElementById("toolbar");
  const filters = document.getElementById("filters");
  const search = document.getElementById("search");
  const empty = document.getElementById("empty");
  const noMatch = document.getElementById("no-match");
  const error = document.getElementById("error");
  const toast = document.getElementById("toast");
  const themeToggle = document.getElementById("theme-toggle");
  const drawer = document.getElementById("drawer");
  const drawerBody = document.getElementById("drawer-body");
  const drawerClose = document.getElementById("drawer-close");
  const backdrop = document.getElementById("drawer-backdrop");

  const text = value => String(value ?? "");
  const escape = value => text(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
  const asset = path => !path ? "" : (/^(https?:)?\/\//.test(path) || path.startsWith("/") ? path : base + path.replace(/^\.?\//, ""));
  const list = value => Array.isArray(value) ? value.map(text).filter(Boolean) : [];
  const year = value => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : 0;

  let works = [];
  let activeType = "All";
  let keyword = "";
  let lastFocus = null;

  const normalize = work => ({
    title: text(work.title),
    tagline: text(work.tagline),
    summary: text(work.summary),
    type: text(work.type) || "Project",
    year: year(work.year),
    period: text(work.period),
    role: text(work.role),
    status: text(work.status),
    tech: list(work.tech),
    highlights: list(work.highlights),
    cover: text(work.cover),
    url: text(work.url),
    repo: text(work.repo),
    note: text(work.note)
  });

  /* ---------- cover fallbacks ---------- */
  function monogram(title) {
    const trimmed = title.trim();
    if (!trimmed) return "◇";
    const first = trimmed[0];
    return /[a-z0-9]/i.test(first) ? trimmed.slice(0, 2).toUpperCase() : first;
  }

  /* 封面：有图用图，图缺失或加载失败时回退到首字母占位块 */
  function coverMarkup(work) {
    const image = work.cover
      ? `<img src="${escape(asset(work.cover))}" alt="${escape(work.title)}" loading="lazy" decoding="async">`
      : "";
    const fallback = `<span class="thumb-empty"${work.cover ? " hidden" : ""}>${escape(monogram(work.title))}</span>`;
    return image + fallback;
  }

  function bindCovers(root) {
    root.querySelectorAll("img").forEach(image => {
      const showFallback = () => {
        const placeholder = image.parentElement.querySelector(".thumb-empty");
        image.hidden = true;
        if (placeholder) placeholder.hidden = false;
      };
      image.addEventListener("error", showFallback);
      if (image.complete && image.naturalWidth === 0) showFallback();
    });
  }

  /* ---------- rendering ---------- */
  function cardMarkup(work, index) {
    const meta = [work.role, work.year || work.period].filter(Boolean);
    const peek = work.tagline || work.summary;
    return [
      `<article class="works-card" data-index="${index}">`,
      `<button class="card-head" type="button" aria-label="查看 ${escape(work.title)} 详情">`,
      `<span class="thumb">`,
      coverMarkup(work),
      `<span class="thumb-tag">${escape(work.type)}</span>`,
      peek ? `<span class="thumb-peek">${escape(peek)}</span>` : "",
      `<span class="thumb-link" aria-hidden="true">↗</span>`,
      `</span>`,
      `</button>`,
      `<div class="card-body">`,
      `<h2 class="card-title">${escape(work.title)}</h2>`,
      work.tagline ? `<p class="card-tagline">${escape(work.tagline)}</p>` : "",
      meta.length
        ? `<p class="card-meta">${meta.map(item => `<span>${escape(item)}</span>`).join("")}</p>`
        : "",
      `</div>`,
      `</article>`
    ].join("");
  }

  function visibleWorks() {
    const needle = keyword.trim().toLocaleLowerCase();
    return works.filter(work => {
      if (activeType !== "All" && work.type !== activeType) return false;
      if (!needle) return true;
      const haystack = [work.title, work.tagline, work.summary, work.type, work.role]
        .concat(work.tech, work.highlights)
        .join(" ")
        .toLocaleLowerCase();
      return haystack.includes(needle);
    });
  }

  function render() {
    const shown = visibleWorks();
    grid.innerHTML = shown.map(work => cardMarkup(work, works.indexOf(work))).join("");
    bindCovers(grid);
    grid.querySelectorAll(".card-head").forEach(button => {
      button.addEventListener("click", () => {
        openDrawer(works[Number(button.closest(".works-card").dataset.index)], button);
      });
    });
    noMatch.hidden = shown.length !== 0 || works.length === 0;
  }

  function renderFilters() {
    if (!works.length) {
      toolbar.hidden = true;
      return;
    }
    toolbar.hidden = false;
    const groups = works.reduce((acc, work) => {
      acc[work.type] = (acc[work.type] || 0) + 1;
      return acc;
    }, {});
    const entries = [["All", works.length]].concat(Object.keys(groups).sort().map(type => [type, groups[type]]));
    filters.innerHTML = entries.map(([label, total]) =>
      `<button class="chip" type="button" data-type="${escape(label)}" aria-pressed="${label === activeType}">${escape(label)}<b>${total}</b></button>`
    ).join("");
    filters.querySelectorAll(".chip").forEach(chip => {
      chip.addEventListener("click", () => {
        activeType = chip.dataset.type;
        filters.querySelectorAll(".chip").forEach(item => {
          item.setAttribute("aria-pressed", String(item === chip));
        });
        render();
      });
    });
  }

  function renderSummary() {
    const years = works.map(work => work.year).filter(Boolean).sort((a, b) => a - b);
    count.textContent = works.length
      ? `${works.length} ${works.length === 1 ? "project" : "projects"}`
      : "";
    range.textContent = !years.length ? ""
      : years[0] === years[years.length - 1] ? String(years[0])
      : `${years[0]} — ${years[years.length - 1]}`;
    empty.hidden = works.length !== 0;
  }

  /* ---------- drawer ---------- */
  let activeWork = null;

  /* 站内链接（如 /music/）保持当前标签页，外部链接新开标签 */
  const linkAttrs = value => value.startsWith("/") ? "" : ' target="_blank" rel="noopener noreferrer"';

  function drawerMarkup(work) {
    const meta = [work.status, work.role, work.period || work.year].filter(Boolean);
    return [
      work.cover
        ? `<div class="detail-hero">${coverMarkup(work)}</div>`
        : "",
      `<span class="detail-tag">${escape(work.type)}</span>`,
      `<h2 class="detail-title" id="drawer-title">${escape(work.title)}</h2>`,
      work.tagline ? `<p class="detail-tagline">${escape(work.tagline)}</p>` : "",
      meta.length
        ? `<ul class="detail-meta">${meta.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.tech.length
        ? `<ul class="detail-stack">${work.tech.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.summary ? `<p class="detail-body">${escape(work.summary)}</p>` : "",
      work.highlights.length
        ? `<h3 class="detail-h">做了什么</h3><ul class="detail-list">${work.highlights.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.note ? `<p class="detail-note">${escape(work.note)}</p>` : "",
      `<div class="detail-links">`,
      work.url ? `<a class="detail-link primary" href="${escape(asset(work.url))}"${linkAttrs(asset(work.url))}>查看项目 ↗</a>` : "",
      work.repo
        ? `<button class="detail-link" id="copy-repo" type="button" data-repo="${escape(work.repo)}">复制源码地址</button>`
        : "",
      !work.url && !work.repo ? `<span class="detail-note">还没有填写项目链接，在 works.json 里补上 url 或 repo 即可。</span>` : "",
      `</div>`
    ].join("");
  }

  function openDrawer(work, trigger) {
    if (!work) return;
    activeWork = work;
    lastFocus = trigger || document.activeElement;
    drawerBody.innerHTML = drawerMarkup(work);
    bindCovers(drawerBody);
    bindCopy();
    drawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-visible");
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    drawer.scrollTop = 0;
    drawerClose.focus({ preventScroll: true });
  }

  function closeDrawer() {
    if (!activeWork) return;
    activeWork = null;
    drawer.setAttribute("aria-hidden", "true");
    document.body.classList.remove("drawer-visible");
    document.body.style.overflow = "";
    window.setTimeout(() => {
      backdrop.hidden = true;
      if (!activeWork) drawerBody.innerHTML = "";
    }, 320);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
    lastFocus = null;
  }

  function bindCopy() {
    const button = drawerBody.querySelector("#copy-repo");
    if (!button) return;
    button.addEventListener("click", async () => {
      const value = button.dataset.repo;
      try {
        await navigator.clipboard.writeText(value);
        showToast("源码地址已复制");
      } catch {
        showToast(value);
      }
    });
  }

  let toastTimer = 0;
  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    requestAnimationFrame(() => toast.classList.add("toast-visible"));
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("toast-visible");
      window.setTimeout(() => { toast.hidden = true; }, 300);
    }, 1900);
  }

  /* ---------- loading ---------- */
  async function load() {
    const url = `${base}works.json?v=${DATA_VERSION}`;
    setCollectionLoading(error, "作品数据");
    const result = await fetchCollectionJson(url);

    if (!result.ok) {
      count.textContent = "";
      range.textContent = "";
      toolbar.hidden = true;
      noMatch.hidden = true;
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
    works = result.data.filter(work => work && (work.title || work.cover)).map(normalize);
    renderSummary();
    renderFilters();
    render();
  }

  /* ---------- events ---------- */
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
  let searchTimer = 0;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      keyword = search.value;
      render();
    }, 120);
  });
  drawerClose.addEventListener("click", closeDrawer);
  backdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && activeWork) closeDrawer();
  });
  document.getElementById("year").textContent = new Date().getFullYear();
  load();
})();
