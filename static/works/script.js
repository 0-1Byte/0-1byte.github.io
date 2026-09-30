(() => {
  "use strict";

  /* 目录前缀由脚本自身 URL 推导（见 collection-common.js），
     这样根路径部署与 /sub/ 子目录部署都成立。
     注意两点：
       1. defer 脚本执行时 document.currentScript 为 null，只能反查 script 标签
       2. 用 getAttribute("src") 而不是 .src —— 后者依赖属性反射，取值更稳 */
  const selfScript = document.querySelector('script[src$="/works/script.js?v=3"]')
    || document.querySelector('script[src*="/works/script.js"]');
  const base = derivePageBase(selfScript && selfScript.getAttribute("src"));
  const DATA_VERSION = "3";        // works.json 有更新时改这个数字即可破缓存
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

  /* ---------- 状态（阶段 6） ----------
     统一词表：Idea / Building / Paused / Shipped / Abandoned / Ongoing
     数据里可能写中文（如「已上线」），此时 statusLabel 会保留原文并优先显示，
     颜色按归类后的 canonical 值取。两种写法都能工作。 */
  const STATUS_ORDER = ["Idea", "Building", "Ongoing", "Paused", "Shipped", "Abandoned"];

  const statusKey = work => {
    const canon = text(work.status);
    const hit = STATUS_ORDER.find(v => v.toLowerCase() === canon.toLowerCase());
    return hit ? hit.toLowerCase() : "unknown";
  };

  const statusText = work => text(work.statusLabel) || text(work.status);

  function statusMarkup(work) {
    const label = statusText(work);
    if (!label) return "";
    return `<span class="status" data-status="${statusKey(work)}">`
      + `<span class="status-dot" aria-hidden="true"></span>`
      + `<span class="status-label">${escape(label)}</span>`
      + `</span>`;
  }

  const normalize = work => ({
    title: text(work.title),
    tagline: text(work.tagline),
    summary: text(work.summary),
    type: text(work.type) || "Project",
    year: year(work.year),
    period: text(work.period),
    role: text(work.role),
    status: text(work.status),
    statusLabel: text(work.statusLabel),
    started: text(work.started),
    problem: text(work.problem),
    learned: text(work.learned),
    demo: text(work.demo),
    tech: list(work.tech),
    highlights: list(work.highlights),
    cover: text(work.cover),
    // url 与 demo 等价（spec 里叫 Demo）；两个都填时优先 url
    url: text(work.url) || text(work.demo),
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
    /* 像一份 project archive 条目：
         标题
         一句话说明
         ● Building
         Chrome Extension · JavaScript · Started 2026.09
       状态单独一行并用圆点标示，不与类型/时间混在一起。 */
    const meta = [work.type, ...work.tech.slice(0, 2)].filter(Boolean);
    const started = work.started || work.period;
    const peek = work.tagline || work.summary;
    return [
      `<article class="works-card" data-index="${index}" data-status="${statusKey(work)}">`,
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
      statusMarkup(work),
      meta.length || started
        ? `<p class="card-meta">`
          + meta.map(item => `<span>${escape(item)}</span>`).join("")
          + (started ? `<span>${escape(/^\d{4}/.test(started) ? `Started ${started}` : started)}</span>` : "")
          + `</p>`
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
    const meta = [work.role, work.started || work.period || work.year].filter(Boolean);
    return [
      work.cover
        ? `<div class="detail-hero">${coverMarkup(work)}</div>`
        : "",
      `<span class="detail-tag">${escape(work.type)}</span>`,
      `<h2 class="detail-title" id="drawer-title">${escape(work.title)}</h2>`,
      work.tagline ? `<p class="detail-tagline">${escape(work.tagline)}</p>` : "",
      /* 状态单独放，比混在 meta 里更容易一眼看到 */
      statusMarkup(work) ? `<p class="detail-status">${statusMarkup(work)}</p>` : "",
      meta.length
        ? `<ul class="detail-meta">${meta.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.tech.length
        ? `<ul class="detail-stack">${work.tech.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.summary ? `<p class="detail-body">${escape(work.summary)}</p>` : "",
      /* 阶段 6 新增字段：有值才显示，不编造也不留空标题 */
      work.problem
        ? `<h3 class="detail-h">要解决的问题</h3><p class="detail-body">${escape(work.problem)}</p>`
        : "",
      work.highlights.length
        ? `<h3 class="detail-h">做了什么</h3><ul class="detail-list">${work.highlights.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`
        : "",
      work.learned
        ? `<h3 class="detail-h">学到什么</h3><p class="detail-body">${escape(work.learned)}</p>`
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
  /* 页脚年份：拿不到元素就跳过。
     这里刻意保留非空判断 —— 同一个脚本里若有一句「拿到元素就直接用」
     并在 null 上抛错，会把后面那句加载调用一起带走，整页数据变空。
     那种情况真实发生过（主题切换按钮被移除时）。 */
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
  load();
})();
