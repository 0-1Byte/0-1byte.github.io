(() => {
  "use strict";

  const MUSIC_BASE = "/music/";
  const DATA_VERSION = "3";        // songs.json 有更新时改这个数字即可破缓存
  const EAGER_COUNT = 4;           // Prioritize the first covers; the rest load lazily.
  const WIDTHS = [240, 320, 480];  // 与 optimize_music_covers.py 的产出档位一致

  const grid = document.getElementById("song-grid");
  const count = document.getElementById("song-count");
  const error = document.getElementById("error");
  const selectedTitle = document.getElementById("selected-title");
  const selectedArtist = document.getElementById("selected-artist");
  const selectedCredits = document.getElementById("selected-credits");
  let songs = [];
  let selectedIndex = 0;

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

  /* Keep srcset selection aligned with the responsive sleeve sizes in style.css. */
  const SIZES = "(max-width: 359px) 132px, (max-width: 600px) 150px, (max-width: 850px) 220px, 270px";

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

  function render(songList) {
    songs = songList;
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
      const stackLabel = `<span class="stack-label">${escapeHtml(title)}${artist ? ` <span>${escapeHtml(artist)}</span>` : ""}</span>`;
      const externalLink = song.url
        ? `<a class="external" href="${escapeHtml(song.url)}" target="_blank" rel="noopener noreferrer" aria-label="在新窗口打开 ${escapeHtml(title)}" title="打开歌曲链接">↗</a>`
        : "";

      return `
        <article class="song-card" role="listitem">
          <div class="cover-stage">
            <button class="cover-select" type="button" data-index="${index}" aria-pressed="false" aria-label="选择唱片：${escapeHtml(title)}" tabindex="-1">
              ${image}
              ${stackLabel}
              ${credits}
            </button>
            ${externalLink}
          </div>
        </article>
      `;
    }).join("");

    count.textContent = `${songs.length} ${songs.length === 1 ? "song" : "songs"}`;
    bindCoverFallback();
    if (songs.length) updateWall(Math.min(getWallRadius(), songs.length - 1));
  }

  function bindSelection() {
    grid.addEventListener("click", event => {
      const button = event.target.closest(".cover-select");
      if (!button || !grid.contains(button)) return;
      updateWall(Number(button.dataset.index));
    });

    grid.addEventListener("keydown", event => {
      const button = event.target.closest(".cover-select");
      if (!button) return;
      let nextIndex = Number(button.dataset.index);
      if (event.key === "ArrowLeft") nextIndex = (nextIndex - 1 + songs.length) % songs.length;
      else if (event.key === "ArrowRight") nextIndex = (nextIndex + 1) % songs.length;
      else if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = songs.length - 1;
      else return;
      event.preventDefault();
      updateWall(nextIndex, true);
    });

    document.getElementById("previous-record").addEventListener("click", () => {
      updateWall((selectedIndex - 1 + songs.length) % songs.length);
    });
    document.getElementById("next-record").addEventListener("click", () => {
      updateWall((selectedIndex + 1) % songs.length);
    });
  }

  function updateWall(index, focus = false) {
    if (!songs.length) return;
    selectedIndex = (index + songs.length) % songs.length;
    const radius = getWallRadius();
    const slotStep = Number.parseFloat(getComputedStyle(grid).getPropertyValue("--slot-step")) || 118;
    const selectedSong = songs[selectedIndex];

    grid.querySelectorAll(".song-card").forEach((card, cardIndex) => {
      let offset = cardIndex - selectedIndex;
      if (offset > songs.length / 2) offset -= songs.length;
      if (offset < -songs.length / 2) offset += songs.length;

      const distance = Math.abs(offset);
      const visible = distance <= radius;
      const button = card.querySelector(".cover-select");
      const yaw = offset === 0 ? 0 : Math.sign(-offset) * Math.min(18 + distance * 12, 62);
      const depth = offset === 0 ? 108 : -Math.min(distance * 24, 96);

      card.classList.toggle("is-wall-visible", visible);
      card.classList.toggle("is-selected", offset === 0);
      card.style.setProperty("--offset-x", `${offset * slotStep}px`);
      card.style.setProperty("--yaw", `${yaw}deg`);
      card.style.setProperty("--depth", `${depth}px`);
      card.style.setProperty("--layer", String(20 - distance));
      card.style.setProperty("--cover-opacity", String(Math.max(.78, 1 - distance * .055)));
      card.inert = !visible;
      card.setAttribute("aria-hidden", String(!visible));
      button.setAttribute("aria-pressed", String(offset === 0));
      button.tabIndex = offset === 0 ? 0 : -1;
    });

    selectedTitle.textContent = selectedSong.title;
    selectedArtist.textContent = selectedSong.artist || "";
    selectedCredits.textContent = [
      selectedSong.lyricist && `词 ${selectedSong.lyricist}`,
      selectedSong.composer && `曲 ${selectedSong.composer}`
    ].filter(Boolean).join("  ·  ");

    grid.classList.add("wall-ready");
    if (focus) grid.querySelector(`.cover-select[data-index="${selectedIndex}"]`).focus();
  }

  function getWallRadius() {
    const width = grid.clientWidth;
    return width < 340 ? 1 : width <= 850 ? 2 : 4;
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

  window.addEventListener("storage", event => {
    if (event.key === "pref-theme" && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });

  let resizeTimer = 0;
  const scheduleWallLayout = () => {
    clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => updateWall(selectedIndex), 80);
  };
  window.addEventListener("resize", scheduleWallLayout);
  if ("ResizeObserver" in window) new ResizeObserver(() => updateWall(selectedIndex)).observe(grid);

  /* 页脚年份：拿不到元素就跳过。
     这里刻意保留非空判断 —— 同一个脚本里若有一句「拿到元素就直接用」
     并在 null 上抛错，会把后面那句加载调用一起带走，整页数据变空。
     那种情况真实发生过（主题切换按钮被移除时）。 */
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  bindSelection();
  loadSongs();
})();
