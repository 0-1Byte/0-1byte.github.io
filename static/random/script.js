/* ==========================================================================
   /random/ —— 从全部内容里随机抽取一件

   设计要点
   --------
   1. 统一数据模型（各源结构不同，用 adapter 抹平）：
        { type, label, emoji, title, subtitle, image, url, date, description }
   2. adapter 只做「字段映射 + 图片地址拼接」，不强行让所有源长一样：
      没有的字段就是空，展示层按需省略，不编造内容。
   3. 一次性并行拉取所有源并建立索引；之后每次抽取都是内存操作，瞬时完成。
      额外提供一个「抽完立刻预取另一张封面」的小优化（浏览器自行缓存）。
   4. 三态明确：loading / empty / error，任何失败都显示原因而不是空白。

   数据源与字段依据 tools/audit_sources.py 的实际盘点结果，非猜测。
   ========================================================================== */
(() => {
  "use strict";

  /* ---------------------------------------------------------------
     一、数据源定义 + adapter
     --------------------------------------------------------------- */

  // 图片来源与比例：music 是方形；四个合集页是 2:3 竖版；works 是 16:10
  const SHAPE = { square: "square", portrait: "portrait", wide: "wide" };

  /* 与 static/covers.js 的 resolveAsset 保持同一套规则：
       完整 URL（http/https）或根路径（/…）→ 原样返回
       其余相对路径 → 拼上该内容源自己的目录
     必须一致，否则会出现「少了目录」或「把 URL 当成相对路径」的破图。 */
  function isRemote(path) {
    return /^(https?:)?\/\//.test(path) || String(path).startsWith("/");
  }

  function assetFor(baseDir, path) {
    if (!path) return "";
    return isRemote(path) ? path : `${baseDir}/${path}`;
  }

  const SOURCES = [
    {
      key: "music",
      label: "Music",
      emoji: "🎵",
      kind: "Song",
      file: "/music/songs.json?v=2",
      shape: SHAPE.square,
      assetDir: "/music/assets",
      // songs.json: title / artist / album / year / cover / img / url
      map: (it) => ({
        title: it.title,
        subtitle: it.artist,
        description: it.album ? `专辑《${it.album}》` : "",
        date: it.year,
        image: it.img ? `/music/assets/${it.img}-480.webp` : assetFor("/music", it.cover),
        fallback: assetFor("/music", it.cover),
        url: it.url
      })
    },
    {
      key: "books",
      label: "Books",
      emoji: "📖",
      kind: "Book",
      file: "/book/books.json?v=2",
      shape: SHAPE.portrait,
      assetDir: "/book/covers/opt",
      // books.json: title / author / cover / img / fallbackCover / url
      map: (it) => ({
        title: it.title,
        subtitle: it.author,
        description: it.note || "",
        date: null,
        image: it.img ? `/book/covers/opt/${it.img}-320.webp` : assetFor("/book", it.cover),
        // 有的书名录里 cover 本身就是远程 URL，assetFor 会原样返回
        fallback: assetFor("/book", it.cover) || it.fallbackCover || "",
        url: it.url
      })
    },
    {
      key: "films",
      label: "Films",
      emoji: "🎬",
      kind: "Film",
      file: "/film/films.json?v=2",
      shape: SHAPE.portrait,
      assetDir: "/film/covers/opt",
      // films.json: title / year / cover / img / url
      map: (it) => ({
        title: it.title,
        subtitle: "",
        description: it.note || "",
        date: it.year,
        image: it.img ? `/film/covers/opt/${it.img}-320.webp` : assetFor("/film", it.cover),
        fallback: assetFor("/film", it.cover),
        url: it.url
      })
    },
    {
      key: "tv",
      label: "TV",
      emoji: "📺",
      kind: "TV",
      file: "/tv/tvs.json?v=2",
      shape: SHAPE.portrait,
      assetDir: "/tv/covers/opt",
      map: (it) => ({
        title: it.title,
        subtitle: "",
        description: it.note || "",
        date: it.year,
        image: it.img ? `/tv/covers/opt/${it.img}-320.webp` : assetFor("/tv", it.cover),
        fallback: assetFor("/tv", it.cover),
        url: it.url
      })
    },
    {
      key: "docu",
      label: "Docu",
      emoji: "🎞️",
      kind: "Documentary",
      file: "/docu/docus.json?v=2",
      shape: SHAPE.portrait,
      assetDir: "/docu/covers/opt",
      map: (it) => ({
        title: it.title,
        subtitle: "",
        description: it.note || "",
        date: it.year,
        image: it.img ? `/docu/covers/opt/${it.img}-320.webp` : assetFor("/docu", it.cover),
        fallback: assetFor("/docu", it.cover),
        url: it.url
      })
    },
    {
      key: "works",
      label: "Works",
      emoji: "🛠️",
      kind: "Work",
      file: "/works/works.json?v=2",
      shape: SHAPE.wide,
      assetDir: "/works/assets",
      // works.json: title / tagline / summary / type / year / period / role / cover / url
      // cover 形如 assets/chen-blog.svg —— 相对 works 目录，必须补上 /works/
      map: (it) => ({
        title: it.title,
        subtitle: it.tagline,
        description: it.summary,
        // 作品没有单一日期，用 period（如「2024 — 至今」）更有信息量
        date: it.period || it.year,
        image: assetFor("/works", it.cover),
        fallback: "",
        url: it.url
      })
    },
    {
      // Fragments（阶段 3 定为 pending，尚无数据）。
      // 这里只登记，不新建空数据文件 —— 拉取失败即视为「该源暂无内容」，
      // 因此现在不会出现在筛选里；等 /fragments/fragments.json 就位会自动生效。
      key: "fragments",
      label: "Fragments",
      emoji: "✍️",
      kind: "Fragment",
      file: "/fragments/fragments.json?v=2",
      shape: SHAPE.wide,
      assetDir: "/fragments/assets",
      optional: true,
      map: (it) => ({
        title: it.title,
        subtitle: it.subtitle || "",
        description: it.body || it.description || "",
        date: it.date,
        image: assetFor("/fragments", it.image || it.img),
        fallback: "",
        url: it.url || ""
      })
    }
  ];

  /* ---------------------------------------------------------------
     二、取数
     --------------------------------------------------------------- */

  const slot = document.getElementById("drawer-slot");
  const filtersEl = document.getElementById("filters");
  const actionsEl = document.getElementById("actions");
  const countEl = document.getElementById("random-count");
  const anotherBtn = document.getElementById("another");

  let pool = [];              // 全部条目（统一模型）
  let byKey = {};             // key -> 该源的条目
  let activeKey = "all";
  let current = null;
  let loading = true;
  let lastError = null;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  async function fetchSource(src) {
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 12000) : null;
    try {
      const res = await fetch(src.file, {
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!Array.isArray(data)) throw new Error("顶层不是 JSON 数组");
      return { ok: true, src, items: data };
    } catch (error) {
      return {
        ok: false, src,
        reason: error && error.name === "AbortError" ? "请求超时（12 秒）" : String(error && error.message || error)
      };
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  /* ---------------------------------------------------------------
     三、渲染：状态
     --------------------------------------------------------------- */

  function setSlot(html, state) {
    slot.className = "drawer-slot";
    slot.dataset.state = state || "";
    slot.innerHTML = html;
    // 触发淡入（下一帧加 class）
    requestAnimationFrame(() => slot.classList.add("is-shown"));
  }

  function renderLoading() {
    setSlot(`<div class="drawer-empty" data-state="loading">
        <span class="state-spinner" aria-hidden="true"></span>
        <span>正在打开抽屉…</span>
      </div>`, "loading");
  }

  function renderError(info) {
    setSlot(`<div class="drawer-empty" data-state="error">
        <p class="state-title">抽屉打不开了</p>
        ${info.url ? `<p class="state-row"><span class="state-label">请求地址</span><code>${esc(info.url)}</code></p>` : ""}
        ${info.reason ? `<p class="state-row"><span class="state-label">失败原因</span><span>${esc(info.reason)}</span></p>` : ""}
        <p class="state-row"><span class="state-label">建议</span><span>确认该 JSON 已随站点部署；部分内容源缺失不影响其余内容。</span></p>
      </div>`, "error");
  }

  function renderEmpty() {
    setSlot(`<div class="drawer-empty" data-state="empty">
        <p class="state-title">抽屉里还没有这一类东西</p>
        <p>换一个类型，或等这里添了新内容再来。</p>
      </div>`, "empty");
  }

  function renderItem(item) {
    const shapeClass = item.shape === SHAPE.portrait ? " is-portrait"
      : item.shape === SHAPE.wide ? " is-wide" : "";

    const img = item.image
      ? `<img src="${esc(item.image)}" alt="${esc(item.title)}"
              loading="eager" decoding="async"
              ${item.fallback ? `data-fallback="${esc(item.fallback)}"` : ""}>`
      : "";

    const meta = item.date ? `<p class="drawer-meta">${esc(item.date)}</p>` : "";
    const desc = item.description
      ? `<p class="drawer-desc">${esc(item.description)}</p>` : "";
    const link = item.url
      ? `<a class="drawer-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">查看 ↗</a>`
      : "";

    setSlot(`
      <div class="drawer-thumb${shapeClass}">${img}</div>
      <div class="drawer-body">
        <p class="drawer-type"><span class="drawer-emoji" aria-hidden="true">${esc(item.emoji)}</span>${esc(item.kind)}</p>
        <h2 class="drawer-title">${esc(item.title)}</h2>
        ${item.subtitle ? `<p class="drawer-sub">${esc(item.subtitle)}</p>` : ""}
        ${desc}
        ${meta}
        ${link}
      </div>
    `, "item");

    bindImgFallback();
  }

  /* 衍生图取不到时退回原始封面，避免破图 */
  function bindImgFallback() {
    const img = slot.querySelector("img[data-fallback]");
    if (!img) return;
    img.addEventListener("error", () => {
      const fb = img.getAttribute("data-fallback");
      if (!fb || img.dataset.used) return;
      img.dataset.used = "1";
      img.src = fb;
    });
  }

  /* ---------------------------------------------------------------
     四、渲染：筛选
     --------------------------------------------------------------- */

  function renderFilters() {
    const entries = [["all", "All", pool.length]];
    SOURCES.forEach((src) => {
      const n = (byKey[src.key] || []).length;
      if (n > 0) entries.push([src.key, src.label, n]);
    });

    if (pool.length === 0) {
      filtersEl.hidden = true;
      return;
    }

    filtersEl.hidden = false;
    filtersEl.innerHTML = entries.map(([key, label, n]) =>
      `<button class="chip" type="button" data-key="${esc(key)}"
               aria-pressed="${key === activeKey}">${esc(label)}<b>${n}</b></button>`
    ).join("");

    filtersEl.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        activeKey = chip.dataset.key;
        filtersEl.querySelectorAll(".chip").forEach((c) => {
          c.setAttribute("aria-pressed", String(c === chip));
        });
        pick();
      });
    });

    countEl.textContent = `${pool.length} ${pool.length === 1 ? "thing" : "things"}`;
  }

  /* ---------------------------------------------------------------
     五、抽取
     --------------------------------------------------------------- */

  function candidates() {
    return activeKey === "all" ? pool : (byKey[activeKey] || []);
  }

  function pick() {
    const list = candidates();

    if (list.length === 0) {
      current = null;
      actionsEl.hidden = true;
      renderEmpty();
      return;
    }

    // 避免连续抽到同一件（池子大于 1 时）
    let next = list[Math.floor(Math.random() * list.length)];
    if (list.length > 1 && current && next.title === current.title && next.kind === current.kind) {
      next = list[(list.indexOf(next) + 1) % list.length];
    }

    current = next;
    actionsEl.hidden = false;
    renderItem(next);
  }

  /* ---------------------------------------------------------------
     六、启动
     --------------------------------------------------------------- */

  async function boot() {
    renderLoading();

    const results = await Promise.all(SOURCES.map(fetchSource));
    const failed = [];

    results.forEach((r) => {
      if (!r.ok) {
        failed.push(r);
        return;
      }
      const mapped = r.items
        .map((it) => {
          const base = r.src.map(it) || {};
          return {
            type: r.src.key,
            label: r.src.label,
            emoji: r.src.emoji,
            kind: base.kind || r.src.kind,
            shape: r.src.shape,
            title: String(base.title || "").trim(),
            subtitle: String(base.subtitle || "").trim(),
            description: String(base.description || "").trim(),
            date: base.date || null,
            image: base.image || "",
            fallback: base.fallback || "",
            url: base.url || ""
          };
        })
        .filter((it) => it.title);

      byKey[r.src.key] = mapped;
      pool = pool.concat(mapped);
    });

    loading = false;

    // 只有「必需源」全部失败才认为整页失败；可选源（如 fragments）缺失忽略
    const requiredFailed = failed.filter((f) => !f.src.optional);
    if (pool.length === 0) {
      lastError = requiredFailed[0] || failed[0];
      if (lastError) {
        renderError({ url: lastError.src.file, reason: lastError.reason });
      } else {
        renderEmpty();
      }
      filtersEl.hidden = true;
      actionsEl.hidden = true;
      countEl.textContent = "";
      return;
    }

    // 有源失败但还有内容：照常可用，只把失败记录到 console
    failed.forEach((f) => {
      console.warn(`[random] 内容源 ${f.src.label} 不可用（${f.reason}）—— 已跳过，不影响其余内容。`);
    });

    renderFilters();
    pick();

    // 预取一张封面，下一次抽取更顺滑（浏览器会缓存）
    if (pool.length > 1) {
      const probe = new Image();
      probe.src = pool[0].image || "";
    }
  }

  /* another：点击 或 空格 */
  anotherBtn.addEventListener("click", pick);
  document.addEventListener("keydown", (event) => {
    if (event.key !== " " && event.key !== "Spacebar") return;
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
    if (actionsEl.hidden) return;
    event.preventDefault();
    pick();
  });

  document.getElementById("year").textContent = new Date().getFullYear();
  boot();
})();
