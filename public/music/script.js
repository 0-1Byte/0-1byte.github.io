(() => {
  "use strict";

  const MUSIC_BASE = "/music/";
  const DATA_VERSION = "2";        // songs.json 有更新时改这个数字即可破缓存
  const EAGER_COUNT = 4;           // 首屏优先加载的封面数量（详见下方 CSS 宽度说明）
  const WIDTHS = [240, 320, 480];  // 与 optimize_music_covers.py 的产出档位一致

  const grid = document.getElementById("song-grid");
  const count = document.getElementById("song-count");
  const error = document.getElementById("error");
  const themeToggle = document.getElementById("theme-toggle");

  function safeText(value) {
    return String(value ?? "");
  }

  function escapeHtml(value) {
    return safeText(value).replace(/[&<>"']/g, char => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[char]));
  }

  function resolveAsset(path) {
    if (!path) return "";
    if (/^(https?:)?\/\//.test(path) || path.startsWith("/")) return path;
    return MUSIC_BASE + path.replace(/^\.?\//, "");
  }

  /* 封面网格的显示宽度（CSS 实测）：
       桌面 >850px : 容器 min(1040, 100%-48) 四列，列宽 ≈ 235px
       平板 ≤850px : 三列，列宽 ≈ 234px
       手机 ≤600px : 容器 100%-28，两列，列宽 ≈ 158px
     因此 240w 覆盖 1x 屏，480w 覆盖 2x 屏，320w 是中间档。 */
  const SIZES = "(max-width: 600px) 45vw, (max-width: 850px) 31vw, 235px";

  /* 新版封面：多尺寸 WebP + srcset/sizes，JPG 仅作加载失败兜底。
     img 主干名来自 songs.json（由 tools/optimize_music_covers.py 生成），
     运行期只做简单拼接，不做复杂的字符串转换。 */
  function responsiveCover(song, index, title) {
    const fallback = resolveAsset(song.cover);
    const base = safeText(song.img).trim();
    const eager = index < EAGER_COUNT;

    const loading = eager
      ? 'loading="eager" fetchpriority="high"'
      : 'loading="lazy"';

    if (!base) {
      // 没有衍生图信息（例如老数据）——直接用原图，行为与旧版一致
      return `<img class="cover" src="${escapeHtml(fallback)}" alt="${escapeHtml(title)}" width="480" height="480" ${loading} decoding="async">`;
    }

    const srcset = WIDTHS.map(w => `${MUSIC_BASE}assets/${base}-${w}.webp ${w}w`).join(", ");

    return `<img
          class="cover"
          src="${escapeHtml(`${MUSIC_BASE}assets/${base}-480.webp`)}"
          srcset="${escapeHtml(srcset)}"
          sizes="${escapeHtml(SIZES)}"
          alt="${escapeHtml(title)}"
          width="480" height="480"
          data-fallback="${escapeHtml(fallback)}"
          ${loading}
          decoding="async"
        >`;
  }

  function render(songs) {
    grid.innerHTML = songs.map((song, index) => {
      const title = safeText(song.title);
      const artist = safeText(song.artist);
      const lyricist = safeText(song.lyricist);
      const composer = safeText(song.composer) || "未找到曲作者";

      const image = responsiveCover(song, index, title);

      const credits = `
        <div class="credit-overlay" aria-label="${escapeHtml(`${title} 词曲作者`)}">
          ${lyricist ? `<p><span>词</span>${escapeHtml(lyricist)}</p>` : ""}
          <p><span>曲</span>${escapeHtml(composer)}</p>
        </div>
      `;

      let coverBlock = `<div class="cover-link"><div class="cover-wrap">${image}${credits}</div></div>`;

      if (song.url) {
        coverBlock = `
          <a
            class="cover-link"
            href="${escapeHtml(song.url)}"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="打开 ${escapeHtml(title)}"
          >
            <div class="cover-wrap">
              ${image}
              ${credits}
              <span class="external" aria-hidden="true">↗</span>
            </div>
          </a>
        `;
      }

      return `
        <article class="song-card">
          ${coverBlock}
          <div class="song-info">
            <h2 class="title">${escapeHtml(title)}</h2>
            ${artist ? `<p class="artist">${escapeHtml(artist)}</p>` : ""}
          </div>
        </article>
      `;
    }).join("");

    count.textContent = `${songs.length} ${songs.length === 1 ? "song" : "songs"}`;
    bindCoverFallback();
  }

  /* 万一某个 webp 取不到，退回该首歌的原始 JPG，避免出现破图。 */
  function bindCoverFallback() {
    grid.querySelectorAll("img.cover[data-fallback]").forEach(img => {
      img.addEventListener("error", () => {
        const fallback = img.getAttribute("data-fallback");
        if (!fallback || img.dataset.fallbackUsed) return;
        img.dataset.fallbackUsed = "1";
        img.removeAttribute("srcset");
        img.removeAttribute("sizes");
        img.src = fallback;
      });
    });
  }

  async function loadSongs() {
    const url = `${MUSIC_BASE}songs.json?v=${DATA_VERSION}`;
    setCollectionLoading(error, "歌曲数据");
    // 固定版本号 + 默认缓存：浏览器可以正常复用 songs.json。
    // 首页的 <link rel="preload" as="fetch"> 已经在并行拉取同一 URL。
    const result = await fetchCollectionJson(url);

    if (!result.ok) {
      count.textContent = "";
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
    render(result.data.filter(song => song && song.title && song.cover));
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("pref-theme", theme);
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === "dark" ? "light" : "dark");
  });

  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });

  document.getElementById("year").textContent = new Date().getFullYear();

  loadSongs();
})();
