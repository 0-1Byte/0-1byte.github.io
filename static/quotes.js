/* ==========================================================================
   首屏句子的打字机效果

   手动句子来自首页内联的 #home-quotes；WeRead 只通过 Worker 获取单条随机句子。

   行为：
     · 每次刷新随机抽一句（尽量避开刚看过的那句）
     · 句子立即开始显示；随机背景在后台加载并淡入
     · 打字前按当前宽度与标点/词语边界选好断行，窗口变化时重新排版
     · 一个字符一个字符打出来，速度略有抖动，读起来不像机器
     · 打完后光标停住并变暗（不做无限闪烁，避免抢注意力）
     · 三种状态都有明确表现：
         loading  隐藏句子区并预留稳定空间，避免固定句子首屏闪现
         empty    data/quotes.yaml 为空 -> 显示兜底句
         error    内联数据无效 -> 显示兜底句 + console.warn（不打扰访客）
     · prefers-reduced-motion：直接显示整句，不打字

   用 Array.from 切分字符，这样 emoji 与组合字符不会被劈成两半。
   ========================================================================== */
(() => {
  "use strict";

  const host = document.getElementById("home-focus");
  const textEl = host && host.querySelector("[data-quote-text]");
  const caretEl = host && host.querySelector(".home-focus-caret");
  const sourceEl = document.querySelector("[data-quote-source]");

  if (!textEl) return;

  const reduceMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const backgroundRoot = document.querySelector("[data-home-backgrounds]");
  const backgroundEl = document.querySelector("[data-home-background-image]");
  const quotesEl = document.getElementById("home-quotes");
  const homeTimeEl = document.querySelector("[data-home-time]");
  const homeClockEl = document.querySelector("[data-home-clock]");
  const homeDateEl = document.querySelector("[data-home-date]");
  const homeRoot = host.closest(".home--living");
  const localHost = window.location
    && ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const wereadDevEnabled = Boolean(localHost
    && new URLSearchParams(window.location.search || "").get("wereadDev") === "1");
  const wereadApiBase = wereadDevEnabled
    ? "http://127.0.0.1:8765"
    : String(window.WEREAD_SYNC_API_BASE || "").replace(/\/+$/, "");
  const segmenter = typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter("zh", { granularity: "word" })
    : null;
  const weekdayFormatter = new Intl.DateTimeFormat("en-US", { weekday: "short" });
  const monthFormatter = new Intl.DateTimeFormat("en-US", { month: "short" });

  const FALLBACK = "building small things, thinking about large things.";
  const WEREAD_REQUEST_TIMEOUT_MS = 8000;

  const SEEN_KEY = "home-quote-seen";
  const RECENT_BACKGROUND_KEY = "home-background-recent";
  const CHARS_PER_SEC = 19;          // 基准速度
  const MAX_LEN = 140;               // 超长句子截断，避免打字太久
  let activeItem = null;
  let typingFinished = true;
  let typeTimer = 0;
  let recentBackgrounds = [];
  let measureText = createMeasurer();

  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const lowMotion = reduceMotion
    || (navigator.hardwareConcurrency > 0 && navigator.hardwareConcurrency <= 4)
    || Boolean(connection && (connection.saveData || /(^|-)2g$/.test(connection.effectiveType || "")));
  if (lowMotion && homeRoot) homeRoot.classList.add("home--low-motion");

  function createMeasurer() {
    const style = window.getComputedStyle ? window.getComputedStyle(host) : null;
    const font = style
      ? `${style.fontStyle} ${style.fontVariant} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
      : "34px serif";
    const letterSpacing = style ? parseFloat(style.letterSpacing) || 0 : 0;
    const canvas = document.createElement && document.createElement("canvas");
    const context = canvas && canvas.getContext && canvas.getContext("2d");
    if (context) context.font = font;

    return (text) => {
      if (context) {
        return context.measureText(text).width + Array.from(text).length * letterSpacing;
      }
      return Array.from(text).reduce((width, char) =>
        width + (/[\u2e80-\u9fff\uf900-\ufaff]/.test(char) ? 1 : .55) * 34, 0);
    };
  }

  function tokenize(text) {
    if (segmenter) {
      return Array.from(segmenter.segment(text),
        (part) => part.segment);
    }
    return text.match(/[\u2e80-\u9fff\uf900-\ufaff]|[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*|\s+|./gu) || [];
  }

  function breakPenalty(line, nextToken, currentToken) {
    if (/^[，。！？；：、,.!?;:，」』）》〉】〕］｝”’)]/u.test(nextToken || "")) return Infinity;
    const end = line.trimEnd();
    if (/[，,]$/u.test(end)) return -17;
    if (/[；;：:]$/u.test(end)) return -13;
    if (/[。！？.!?]$/u.test(end)) return -11;
    if (/、$/u.test(end)) return -15;
    if (/\s$/u.test(line)) return 0;
    const currentCjk = /^[\u2e80-\u9fff\uf900-\ufaff]+$/u.test(currentToken || "");
    const nextCjk = /^[\u2e80-\u9fff\uf900-\ufaff]+$/u.test(nextToken || "");
    if (currentCjk && nextCjk && currentToken.length === 1 && nextToken.length === 1) return 16;
    if (/[的了着过和与及把被将而才只不更一]$/u.test(end)) return 11;
    if (/^[的了着过和与及把被]$/u.test(nextToken || "")) return 16;
    if (/[\u2e80-\u9fff\uf900-\ufaff]/u.test(end)) return 2;
    return 0;
  }

  function layoutParagraph(paragraph, width, measure) {
    const tokens = tokenize(paragraph).flatMap((token) =>
      /^[\u2e80-\u9fff\uf900-\ufaff]+$/u.test(token) && measure(token) > width
        ? Array.from(token)
        : [token]
    );
    if (tokens.length < 2 || measure(paragraph) <= width) return [paragraph.trim()];

    const states = Array(tokens.length + 1).fill(null);
    states[0] = { cost: 0, previous: -1 };

    for (let start = 0; start < tokens.length; start += 1) {
      const state = states[start];
      if (!state) continue;
      let line = "";

      for (let end = start; end < tokens.length; end += 1) {
        line += tokens[end];
        const value = line.trim();
        if (!value) continue;
        const lineWidth = measure(value);
        if (lineWidth > width && end > start) break;
        if (lineWidth > width) continue;

        const nextToken = tokens[end + 1] || "";
        const penalty = breakPenalty(line, nextToken, tokens[end]);
        if (penalty === Infinity) continue;

        const isLast = end === tokens.length - 1;
        const raggedness = Math.max(0, (width - lineWidth) / width);
        let cost = state.cost + raggedness * raggedness * (isLast ? 2 : 9);
        if (!isLast) cost += 9 + penalty;

        if (isLast && lineWidth < width * .2) cost += 45;
        if (isLast && /^[\u2e80-\u9fff\uf900-\ufaff]{1,3}[，。！？；：、,.!?;:]?$/u.test(value)) {
          cost += 120;
        }

        const position = end + 1;
        if (!states[position] || cost < states[position].cost) {
          states[position] = {
            cost,
            previous: start,
            value
          };
        }
      }
    }

    if (!states[tokens.length]) return [paragraph.trim()];
    const lines = [];
    let position = tokens.length;
    while (position > 0) {
      const state = states[position];
      lines.push(state.value);
      position = state.previous;
    }
    return lines.reverse();
  }

  function layoutText(text) {
    const width = Math.max(1, (host.clientWidth || 680) - 2);
    return String(text || "").split("\n")
      .flatMap((paragraph) => layoutParagraph(paragraph, width, measureText))
      .join("\n");
  }

  function renderCompletedItem() {
    if (!activeItem) return;
    textEl.textContent = layoutText(String(activeItem.text || "").slice(0, MAX_LEN));
  }

  function handleResize() {
    measureText = createMeasurer();
    if (!activeItem) return;
    if (typingFinished) {
      renderCompletedItem();
      return;
    }

    const visibleCharacters = Array.from(textEl.textContent).filter((char) => char !== "\n").length;
    clearTimeout(typeTimer);
    typeOut(activeItem, visibleCharacters);
  }

  if (window.addEventListener) {
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(handleResize, 120);
    });
  }

  function updateHomeTime() {
    if (!homeTimeEl) return;
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    const weekday = weekdayFormatter.format(now).toUpperCase();
    const month = monthFormatter.format(now).toUpperCase();
    homeTimeEl.dateTime = now.toISOString();
    if (homeClockEl && homeDateEl) {
      homeClockEl.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
      homeDateEl.textContent = `${weekday} / ${month} ${pad(now.getDate())}`;
    }
  }

  function getBackgroundName(path) {
    const filename = String(path).split(/[?#]/, 1)[0].split("/").pop() || "";
    try {
      return decodeURIComponent(filename);
    } catch (error) {
      return filename;
    }
  }

  function pickBackground(backgrounds) {
    let recent = recentBackgrounds;
    try {
      const saved = JSON.parse(localStorage.getItem(RECENT_BACKGROUND_KEY) || "[]");
      if (Array.isArray(saved)) recent = saved.filter((name) => typeof name === "string").slice(0, 2);
    } catch (error) {
      // If storage is blocked, continue with this page's in-memory history.
    }

    const eligible = backgrounds.length > 2
      ? backgrounds.filter((item) => !recent.includes(getBackgroundName(item.src)))
      : backgrounds;
    const selected = eligible[Math.floor(Math.random() * eligible.length)];
    const name = getBackgroundName(selected.src);
    recentBackgrounds = [name, ...recent.filter((previous) => previous !== name)].slice(0, 2);

    try {
      localStorage.setItem(RECENT_BACKGROUND_KEY, JSON.stringify(recentBackgrounds));
    } catch (error) {
      // The in-memory history still prevents repeats until the page is left.
    }
    return selected;
  }

  updateHomeTime();
  setInterval(updateHomeTime, 30000);

  /* ---------- 显示 ---------- */

  /* 数据里若已自带破折号，标记一下，让 CSS 的 ::before 不要重复加前缀。
     pages.css 里的规则是：
       .hero--quote .home-focus-source:not([hidden]):not([data-has-dash])::before
     这样 data/quotes.yaml 的格式与数据都不需要改，
     而源文本自己写了破折号时也不会变成「— — 某某」。 */
  function markSourceDash(source) {
    if (!sourceEl) return;
    const hasDash = /^\s*[—–-]/.test(String(source || ""));
    if (hasDash) sourceEl.setAttribute("data-has-dash", "");
    else sourceEl.removeAttribute("data-has-dash");
  }

  function setSource(source) {
    if (!sourceEl) return;
    if (source) {
      sourceEl.textContent = source;
      sourceEl.hidden = false;
      markSourceDash(source);
    } else {
      sourceEl.textContent = "";
      sourceEl.hidden = true;
      sourceEl.removeAttribute("data-has-dash");
    }
  }

  function showFull(item) {
    activeItem = item;
    typingFinished = true;
    textEl.textContent = layoutText(String(item.text || "").slice(0, MAX_LEN));
    setSource(formatQuoteSource(item));
    if (caretEl) caretEl.classList.add("is-done");
    host.classList.remove("is-loading");
  }

  function showRandomBackground() {
    if (!backgroundEl) return;

    let backgrounds = [];
    try {
      backgrounds = JSON.parse(backgroundRoot && backgroundRoot.getAttribute("data-home-backgrounds") || "[]");
    } catch (error) {
      console.warn("[quotes] 背景图片列表格式无效，使用纯色背景。", error);
      return;
    }
    if (!Array.isArray(backgrounds) || backgrounds.length === 0) return;

    const candidates = backgrounds.filter((background) =>
      background && typeof background.src === "string" && background.src
    );
    if (!candidates.length) return;
    const selected = pickBackground(candidates);
    const mobile = window.matchMedia && window.matchMedia("(max-width: 767px)").matches;
    const canUseOptimized = backgroundRoot
      && backgroundRoot.getAttribute("data-home-backgrounds-optimized") === "true"
      && !/\.svg$/i.test(selected.src);
    const variant = mobile ? "mobile" : "desktop";
    const source = canUseOptimized
      ? selected.src
        .replace(/(^|\/)home\/backgrounds\//, "$1home/backgrounds-optimized/")
        .replace(/\.(jpe?g|png|webp)$/i,
          (_, extension) => `--${extension.toLowerCase()}--${variant}.webp`)
      : selected.src;
    let activeSource = source;
    const showLoadedBackground = () => {
      if (backgroundEl.naturalWidth > 0) backgroundEl.classList.add("is-visible");
    };
    const showBackgroundError = () => {
      if (activeSource !== selected.src) {
        console.warn(`[quotes] 背景图片加载失败（${activeSource}），改用原图。`);
        activeSource = selected.src;
        backgroundEl.addEventListener("error", showBackgroundError, { once: true });
        backgroundEl.src = activeSource;
        return;
      }
      console.warn(`[quotes] 背景图片加载失败（${activeSource}），保留基础深色背景。`);
    };

    backgroundEl.setAttribute("fetchpriority", "high");
    backgroundEl.addEventListener("load", showLoadedBackground, { once: true });
    backgroundEl.addEventListener("error", showBackgroundError, { once: true });
    backgroundEl.src = source;
    if (backgroundEl.complete) showLoadedBackground();
  }

  /* 打字：用 setTimeout 递归而不是 setInterval，
     这样每步可以带一点随机抖动，停顿更像自然书写 */
  function typeOut(item, visibleCharacters = 0) {
    activeItem = item;
    typingFinished = false;
    const chars = Array.from(layoutText(String(item.text || "").slice(0, MAX_LEN)));
    setSource(formatQuoteSource(item));
    if (caretEl) caretEl.classList.remove("is-done");

    if (!chars.length) {
      showFull({ text: FALLBACK, source: "" });
      return;
    }

    let i = 0;
    let countedCharacters = 0;
    while (i < chars.length && countedCharacters < visibleCharacters) {
      if (chars[i] !== "\n") countedCharacters += 1;
      i += 1;
    }
    textEl.textContent = chars.slice(0, i).join("");
    host.classList.remove("is-loading");
    if (i >= chars.length) {
      if (caretEl) caretEl.classList.add("is-done");
      typingFinished = true;
      typeTimer = 0;
      return;
    }

    const step = () => {
      // 一次打 1 个字符；标点后稍作停顿，读起来有呼吸
      textEl.textContent += chars[i];
      const ch = chars[i];
      i += 1;

      if (i >= chars.length) {
        if (caretEl) caretEl.classList.add("is-done");
        typingFinished = true;
        typeTimer = 0;
        return;
      }

      let delay = 1000 / CHARS_PER_SEC;
      delay *= 0.72 + Math.random() * 0.56;                 // 抖动
      if ("，。！？；：、,.!?;:".includes(ch)) delay += 150;  // 标点后停顿
      typeTimer = setTimeout(step, delay);
    };

    typeTimer = setTimeout(step, 220);
  }

  /* ---------- 抽签 ---------- */

  function pick(list) {
    if (!Array.isArray(list) || !list.length) return null;
    if (list.length === 1) return list[0];
    let seen = "";
    try { seen = localStorage.getItem(SEEN_KEY) || ""; } catch (e) { /* 隐私模式 */ }

    for (let attempt = 0; attempt < 8; attempt += 1) {
      const c = list[Math.floor(Math.random() * list.length)];
      if (String(c.text) !== seen) {
        try { localStorage.setItem(SEEN_KEY, String(c.text)); } catch (e) { /* 忽略 */ }
        return c;
      }
    }
    const c = list[Math.floor(Math.random() * list.length)];
    try { localStorage.setItem(SEEN_KEY, String(c.text)); } catch (e) { /* 忽略 */ }
    return c;
  }

  function normalizeQuote(candidate, sourceType) {
    if (!candidate || typeof candidate !== "object") return null;
    const text = String(candidate.text || "").replace(/\s*\|\s*/g, "\n").trim();
    if (!text) return null;
    const type = String(candidate.source_type || (sourceType === "manual" ? "manual" : ""));
    if (type !== sourceType) return null;
    return {
      text,
      source_type: type,
      source: String(candidate.source || "").trim(),
      author: String(candidate.author || "").trim(),
      chapter: String(candidate.chapter || "").trim(),
      also_sources: Array.isArray(candidate.also_sources)
        ? candidate.also_sources.filter((source) => source && typeof source === "object")
        : []
    };
  }

  function buildQuoteSources(data) {
    const sources = [];
    const appendSource = (key, items) => {
      const list = Array.isArray(items)
        ? items.map((item) => normalizeQuote(item, key)).filter(Boolean)
        : [];
      if (list.length) sources.push({ key, items: list });
    };

    if (Array.isArray(data)) {
      appendSource("manual", data);
      return sources;
    }
    if (data && typeof data === "object") {
      if (data.manual !== undefined) {
        appendSource("manual", data.manual);
        return sources;
      }
      appendSource("manual", data.quotes);
      if (!sources.length) {
        const fallback = Object.keys(data).flatMap((key) => Array.isArray(data[key]) ? data[key] : []);
        appendSource("manual", fallback);
      }
    }
    return sources;
  }

  function formatQuoteSource(item) {
    if (item.source_type !== "weread") return item.source || "";
    const allSources = [{
      source: item.source,
      author: item.author,
      chapter: item.chapter
    }, ...item.also_sources];
    const lines = [];
    const seen = new Set();
    allSources.forEach((source) => {
      if (!source || typeof source !== "object") return;
      const title = String(source.source || "").trim();
      const author = String(source.author || "").trim();
      const chapter = String(source.chapter || "").trim();
      const parts = [];
      if (title) parts.push(`《${title}》`);
      if (author) parts.push(author);
      if (chapter) parts.push(chapter);
      const line = parts.join(" · ");
      if (line && !seen.has(line)) {
        seen.add(line);
        lines.push(line);
      }
    });
    return lines.join("；");
  }

  function selectQuote(data) {
    const sources = buildQuoteSources(data);
    const manual = sources.find((source) => source.key === "manual");
    return manual ? pick(manual.items) : null;
  }

  /* ---------- 取数 ---------- */

  function normalizeRemoteQuote(candidate) {
    if (!candidate || typeof candidate !== "object"
      || candidate.source_type !== "weread"
      || typeof candidate.text !== "string" || !candidate.text.trim()
      || candidate.text.length > 20000) return null;
    return {
      text: candidate.text.trim(),
      source_type: "weread",
      source: typeof candidate.source === "string" ? candidate.source.trim().slice(0, 2000) : "",
      author: typeof candidate.author === "string" ? candidate.author.trim().slice(0, 2000) : "",
      chapter: typeof candidate.chapter === "string" ? candidate.chapter.trim().slice(0, 2000) : "",
      also_sources: []
    };
  }

  async function fetchWereadQuote() {
    if (!wereadApiBase || wereadApiBase.includes("REPLACE_WITH_")) return null;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    let timeout = 0;
    let timedOut = false;
    const diagnoseFailure = (reason, status) => {
      if (reason === "http_status") {
        console.warn("[quotes] WeRead request failed: http_status", status);
      } else {
        console.warn("[quotes] WeRead request failed:", reason);
      }
      return null;
    };
    try {
      const timeoutResult = new Promise((resolve) => {
        timeout = setTimeout(() => {
          timedOut = true;
          if (controller) controller.abort();
          resolve({ failure: "timeout" });
        }, WEREAD_REQUEST_TIMEOUT_MS);
      });
      const quoteResult = fetch(`${wereadApiBase}/public/quote`, {
        method: "GET",
        credentials: "omit",
        cache: "no-store",
        headers: { Accept: "application/json" },
        ...(controller ? { signal: controller.signal } : {})
      }).then(async (response) => {
        if (!response.ok) return { failure: "http_status", status: response.status };
        if (Number(response.headers.get("Content-Length") || 0) > 96 * 1024) {
          return { failure: "response_too_large" };
        }
        if (!/application\/json/i.test(response.headers.get("Content-Type") || "")) {
          return { failure: "invalid_content_type" };
        }
        const body = await response.text();
        if (body.length > 96 * 1024) return { failure: "response_too_large" };
        let parsed;
        try {
          parsed = JSON.parse(body);
        } catch (_) {
          return { failure: "invalid_json" };
        }
        const item = normalizeRemoteQuote(parsed);
        return item ? { item } : { failure: "invalid_quote" };
      }).catch(() => ({ failure: timedOut ? "timeout" : "network_error" }));
      const result = await Promise.race([quoteResult, timeoutResult]);
      if (result.failure) return diagnoseFailure(result.failure, result.status);
      return result.item;
    } finally {
      if (timeout) clearTimeout(timeout);
    }
  }

  async function loadQuotes() {
    let manualItem = null;
    try {
      const data = JSON.parse(quotesEl && quotesEl.textContent || "null");
      if (!Array.isArray(data)
        && (!data || typeof data !== "object" || !Array.isArray(data.manual))) {
        throw new Error("invalid_manual_quote_shape");
      }
      manualItem = selectQuote(data);
    } catch (_) {
      console.warn("[quotes] 手动句子数据无效。");
    }

    const chooseWeread = Boolean(wereadApiBase)
      && (!manualItem || Math.random() >= 0.5);
    const wereadItem = chooseWeread ? await fetchWereadQuote() : null;
    const item = wereadItem || manualItem;
    if (item) {
      if (reduceMotion) showFull(item);
      else typeOut(item);
    } else {
      showFull({ text: FALLBACK, source: "" });
    }
  }
// 页面切走时停掉打字，避免回来接着打
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && typeTimer) {
      clearTimeout(typeTimer);
      typeTimer = 0;
    } else if (!document.hidden && activeItem && !typingFinished && !typeTimer) {
      const visibleCharacters = Array.from(textEl.textContent)
        .filter((char) => char !== "\n").length;
      typeOut(activeItem, visibleCharacters);
    }
  });

  loadQuotes();
  showRandomBackground();
})();
