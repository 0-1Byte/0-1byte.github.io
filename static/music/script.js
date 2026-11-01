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
  const search = document.getElementById("music-search");
  const searchInput = document.getElementById("music-search-input");
  const searchToggle = document.getElementById("music-search-toggle");
  const searchClear = document.getElementById("music-search-clear");
  const searchResults = document.getElementById("music-search-results");
  let songs = [];
  let searchCatalog = [];
  let selectedIndex = 0;
  let searchMatches = [];
  let activeSearchIndex = -1;

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

  function normalizeSearchText(value) {
    return safeText(value)
      .normalize("NFKC")
      .toLocaleLowerCase()
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .replace(/[\p{P}\p{S}\s]/gu, "");
  }

  function tokenizeSearchText(value) {
    return safeText(value)
      .normalize("NFKC")
      .toLocaleLowerCase()
      .split(/[\p{P}\p{S}\s]+/u)
      .map(normalizeSearchText)
      .filter(Boolean);
  }

  function editDistanceAtMostOne(left, right) {
    const a = Array.from(left);
    const b = Array.from(right);
    if (Math.abs(a.length - b.length) > 1) return false;

    let i = 0;
    let j = 0;
    let edits = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        i++;
        j++;
        continue;
      }

      if (++edits > 1) return false;
      if (a.length > b.length) i++;
      else if (b.length > a.length) j++;
      else if (a[i] === b[j + 1] && a[i + 1] === b[j]) {
        i += 2;
        j += 2;
      } else {
        i++;
        j++;
      }
    }

    return edits + Number(i < a.length || j < b.length) <= 1;
  }

  function getSearchScore(entry, query, terms) {
    let score = 0;
    const fields = [
      { value: entry.title, tokens: entry.titleTokens, weight: 3 },
      { value: entry.artist, tokens: entry.artistTokens, weight: 2 },
      { value: entry.album, tokens: entry.albumTokens, weight: 1 }
    ];

    for (const field of fields) {
      if (query === field.value) score = Math.max(score, 1000 * field.weight);
      else if (query.length >= 2 && field.value.startsWith(query)) {
        score = Math.max(score, 750 * field.weight);
      } else if (query.length >= 2 && field.value.includes(query)) {
        score = Math.max(score, 600 * field.weight);
      }
    }

    for (const term of terms) {
      let termScore = 0;
      for (const field of fields) {
        if (field.value === term || field.tokens.includes(term)) {
          termScore = Math.max(termScore, 120 * field.weight);
          continue;
        }

        if (field.value.startsWith(term) || field.tokens.some(token => token.startsWith(term))) {
          termScore = Math.max(termScore, 90 * field.weight);
          continue;
        }

        if (field.value.includes(term) || field.tokens.some(token => token.includes(term))) {
          termScore = Math.max(termScore, 70 * field.weight);
          continue;
        }

        if (term.length >= 4 && field.tokens.some(token =>
          Math.abs(Array.from(token).length - Array.from(term).length) <= 1
            && editDistanceAtMostOne(token, term))) {
          termScore = Math.max(termScore, 35 * field.weight);
        }
      }

      if (!termScore) return 0;
      score += termScore;
    }

    return score;
  }

  function searchSongs(query) {
    const normalizedQuery = normalizeSearchText(query);
    const terms = tokenizeSearchText(query);
    if (!normalizedQuery || !terms.length) return [];

    return searchCatalog
      .map(entry => ({ index: entry.index, score: getSearchScore(entry, normalizedQuery, terms) }))
      .filter(match => match.score > 0)
      .sort((a, b) => b.score - a.score || a.index - b.index);
  }

  function renderSearchResults() {
    const query = searchInput.value.trim();
    searchClear.hidden = !query;
    searchMatches = searchSongs(query);
    activeSearchIndex = searchMatches.length ? 0 : -1;

    if (!query) {
      searchResults.replaceChildren();
      searchResults.classList.remove("is-visible");
      searchResults.setAttribute("aria-hidden", "true");
      searchInput.setAttribute("aria-expanded", "false");
      searchInput.removeAttribute("aria-activedescendant");
      return;
    }

    const countLabel = searchMatches.length > 6
      ? `<div class="music-search-count">${searchMatches.length} results</div>`
      : "";
    const rows = searchMatches.map((match, resultIndex) => {
      const song = songs[match.index];
      return `
        <button class="music-search-result${resultIndex === activeSearchIndex ? " is-active" : ""}" type="button" role="option" id="music-search-option-${match.index}" data-song-index="${match.index}" aria-selected="${resultIndex === activeSearchIndex}">
          <span class="music-search-result-title">${escapeHtml(song.title)}</span>
          <span class="music-search-result-artist">${escapeHtml(song.artist || "")}</span>
        </button>
      `;
    }).join("");

    searchResults.innerHTML = searchMatches.length
      ? `${countLabel}<div class="music-search-options">${rows}</div>`
      : '<p class="music-search-empty">No matching songs</p>';
    searchResults.classList.add("is-visible");
    searchResults.setAttribute("aria-hidden", "false");
    searchInput.setAttribute("aria-expanded", "true");
    if (activeSearchIndex >= 0) {
      searchInput.setAttribute("aria-activedescendant", `music-search-option-${searchMatches[activeSearchIndex].index}`);
    } else {
      searchInput.removeAttribute("aria-activedescendant");
    }
  }

  function setActiveSearchResult(index) {
    if (!searchMatches.length) return;
    activeSearchIndex = (index + searchMatches.length) % searchMatches.length;
    const options = searchResults.querySelectorAll(".music-search-result");
    options.forEach((option, optionIndex) => {
      const active = optionIndex === activeSearchIndex;
      option.classList.toggle("is-active", active);
      option.setAttribute("aria-selected", String(active));
    });

    const match = searchMatches[activeSearchIndex];
    searchInput.setAttribute("aria-activedescendant", `music-search-option-${match.index}`);
    searchResults.querySelector(".is-active")?.scrollIntoView({ block: "nearest" });
  }

  function closeSearch({ restoreFocus = false } = {}) {
    search.classList.remove("is-expanded");
    searchToggle.setAttribute("aria-expanded", "false");
    searchToggle.setAttribute("aria-label", "Open song search");
    searchInput.value = "";
    renderSearchResults();
    if (restoreFocus) searchToggle.focus();
  }

  function selectSearchResult(index) {
    if (!Number.isInteger(index) || index < 0 || index >= songs.length) return;
    updateWall(index);
    closeSearch();
  }

  function bindSearch() {
    searchToggle.addEventListener("click", () => {
      if (search.classList.contains("is-expanded")) {
        if (searchInput.value.trim()) {
          searchInput.focus();
          return;
        }
        closeSearch();
        return;
      }

      search.classList.add("is-expanded");
      searchToggle.setAttribute("aria-expanded", "true");
      searchToggle.setAttribute("aria-label", "Close song search");
      searchInput.focus();
    });

    searchInput.addEventListener("input", renderSearchResults);
    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      renderSearchResults();
      searchInput.focus();
    });

    searchInput.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSearch({ restoreFocus: true });
      } else if (event.key === "ArrowDown" && searchMatches.length) {
        event.preventDefault();
        setActiveSearchResult(activeSearchIndex + 1);
      } else if (event.key === "ArrowUp" && searchMatches.length) {
        event.preventDefault();
        setActiveSearchResult(activeSearchIndex - 1);
      } else if (event.key === "Enter" && activeSearchIndex >= 0) {
        event.preventDefault();
        selectSearchResult(searchMatches[activeSearchIndex].index);
      }
    });

    searchResults.addEventListener("click", event => {
      const result = event.target.closest(".music-search-result");
      if (!result || !searchResults.contains(result)) return;
      selectSearchResult(Number(result.dataset.songIndex));
    });

    document.addEventListener("pointerdown", event => {
      if (!search.contains(event.target) && search.classList.contains("is-expanded")) closeSearch();
    });
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
    searchCatalog = songs.map((song, index) => {
      const title = safeText(song.title);
      const artist = safeText(song.artist);
      const album = safeText(song.album);
      return {
        index,
        title: normalizeSearchText(title),
        artist: normalizeSearchText(artist),
        album: normalizeSearchText(album),
        titleTokens: tokenizeSearchText(title),
        artistTokens: tokenizeSearchText(artist),
        albumTokens: tokenizeSearchText(album)
      };
    });
    grid.innerHTML = songs.map((song, index) => {
      const title = safeText(song.title);
      const lyricist = safeText(song.lyricist);
      const composer = safeText(song.composer) || "未找到曲作者";
      const image = responsiveCover(song, index, title);

      const credits = `
        <div class="credit-overlay" aria-label="${escapeHtml(`${title} 词曲作者`)}">
          ${lyricist ? `<p><span>词</span>${escapeHtml(lyricist)}</p>` : ""}
          <p><span>曲</span>${escapeHtml(composer)}</p>
        </div>
      `;
      const externalLink = song.url
        ? `<a class="external" href="${escapeHtml(song.url)}" target="_blank" rel="noopener noreferrer" aria-label="在新窗口打开 ${escapeHtml(title)}" title="打开歌曲链接">↗</a>`
        : "";

      return `
        <article class="song-card" role="listitem">
          <div class="cover-stage">
            <button class="cover-select" type="button" data-index="${index}" aria-pressed="false" aria-label="选择唱片：${escapeHtml(title)}" tabindex="-1">
              <span class="cover-side cover-side--left" aria-hidden="true"></span>
              <span class="cover-side cover-side--right" aria-hidden="true"></span>
              <span class="cover-face">
                ${image}
                ${credits}
              </span>
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
    let swipeStart = null;
    let suppressClick = false;

    const clampIndex = value => {
      if (!songs.length) return 0;
      return Math.min(Math.max(value, 0), songs.length - 1);
    };

    const resetSwipe = () => {
      swipeStart = null;
    };

    grid.addEventListener("click", event => {
      if (suppressClick) {
        suppressClick = false;
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      const button = event.target.closest(".cover-select");
      if (!button || !grid.contains(button)) return;
      updateWall(Number(button.dataset.index));
    });

    grid.addEventListener("pointerdown", event => {
      if (event.pointerType !== "touch") return;
      if (swipeStart) return;
      swipeStart = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        moved: false
      };
    });

    grid.addEventListener("pointermove", event => {
      if (!swipeStart || event.pointerId !== swipeStart.pointerId) return;
      const dx = event.clientX - swipeStart.startX;
      const dy = event.clientY - swipeStart.startY;
      if (Math.abs(dx) >= 8 || Math.abs(dy) >= 8) swipeStart.moved = true;
      if (Math.abs(dx) > Math.abs(dy) * 1.25 && Math.abs(dx) >= 40) {
        swipeStart.horizontal = true;
      }
    });

    grid.addEventListener("pointerup", event => {
      if (!swipeStart || event.pointerId !== swipeStart.pointerId) return;

      const dx = event.clientX - swipeStart.startX;
      const dy = event.clientY - swipeStart.startY;
      const isHorizontalSwipe = Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.25;
      if (isHorizontalSwipe) {
        const direction = dx < 0 ? 1 : -1;
        const nextIndex = clampIndex(selectedIndex + direction);
        if (nextIndex !== selectedIndex) {
          suppressClick = true;
          updateWall(nextIndex);
        }
      }

      resetSwipe();
    });

    grid.addEventListener("pointercancel", resetSwipe);

    grid.addEventListener("keydown", event => {
      const button = event.target.closest(".cover-select");
      if (!button) return;
      let nextIndex = Number(button.dataset.index);
      if (event.key === "ArrowLeft") nextIndex = clampIndex(nextIndex - 1);
      else if (event.key === "ArrowRight") nextIndex = clampIndex(nextIndex + 1);
      else if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = songs.length - 1;
      else return;
      event.preventDefault();
      updateWall(nextIndex, true);
    });

    document.getElementById("previous-record").addEventListener("click", () => {
      updateWall(selectedIndex - 1);
    });
    document.getElementById("next-record").addEventListener("click", () => {
      updateWall(selectedIndex + 1);
    });
  }

  function updateWall(index, focus = false) {
    if (!songs.length) return;
    selectedIndex = Math.min(Math.max(index, 0), songs.length - 1);
    grid.scrollLeft = 0;
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
      const direction = Math.sign(-offset);
      const compact = grid.clientWidth <= 600;
      const yaw = offset === 0 ? -10 : direction * Math.min(22 + distance * 10, 66);
      const depth = offset === 0 ? (compact ? 92 : 108) : -Math.min(distance * (compact ? 27 : 32), compact ? 86 : 112);
      const vertical = distance === 0 ? 0 : -Math.min(distance * 2.5, 9);
      const scale = 1 - Math.min(distance * .035, .14);
      const thickness = Math.max(compact ? 2 : 2.4, (compact ? 3.6 : 4.6) - distance * (compact ? .42 : .55));

      card.classList.toggle("is-wall-visible", visible);
      card.classList.toggle("is-selected", offset === 0);
      card.style.setProperty("--offset-x", `${offset * slotStep}px`);
      card.style.setProperty("--offset-y", `${vertical}px`);
      card.style.setProperty("--yaw", `${yaw}deg`);
      card.style.setProperty("--depth", `${depth}px`);
      card.style.setProperty("--scale", String(scale));
      card.style.setProperty("--sleeve-thickness", `${thickness}px`);
      card.style.setProperty("--sleeve-half-thickness", `${thickness / 2}px`);
      card.style.setProperty("--sleeve-negative-half-thickness", `${thickness / -2}px`);
      card.style.setProperty("--cast-shadow", String(offset === 0 ? .25 : Math.max(.11, .2 - distance * .022)));
      card.style.setProperty("--layer", String(20 - distance));
      card.style.setProperty("--cover-opacity", String(Math.max(.78, 1 - distance * .055)));
      card.inert = !visible;
      card.setAttribute("aria-hidden", String(!visible));
      button.setAttribute("aria-pressed", String(offset === 0));
      button.tabIndex = offset === 0 ? 0 : -1;
    });

    selectedTitle.textContent = selectedSong.title;

    grid.classList.add("wall-ready");
    if (focus) grid.querySelector(`.cover-select[data-index="${selectedIndex}"]`).focus({ preventScroll: true });
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
  bindSearch();
  loadSongs();
})();
