/* ==========================================================================
   首屏句子的打字机效果

   数据来源：/nav.json 里的 quotes 数组（由 Hugo 从 data/quotes.yaml 生成）。
   为什么和导航共用一个端点：Hugo 的首页多个自定义输出格式共用同一个模板
   （按 kind 而不是格式名找模板），而 site-nav.js 已经会拉这个文件 ——
   让句子复用它，可以少发一个请求，也不用再造一个只是名字好看的端点。

   行为：
     · 每次刷新随机抽一句（尽量避开刚看过的那句）
     · 一个字符一个字符打出来，速度略有抖动，读起来不像机器
     · 打完后光标停住并变暗（不做无限闪烁，避免抢注意力）
     · 三种状态都有明确表现：
         loading  保留服务端渲染的那句（页面不会空白）
         empty    data/quotes.yaml 为空 -> 用兜底句
         error    请求失败 -> 保留现有文案 + console.warn（不打扰访客）
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

  // 服务端已经渲染了一句，先留着；拿到数据后再换掉
  const serverText = textEl.textContent || "";
  const FALLBACK = serverText || "building small things, thinking about large things.";

  const SEEN_KEY = "home-quote-seen";
  const CHARS_PER_SEC = 19;          // 基准速度
  const MAX_LEN = 140;               // 超长句子截断，避免打字太久

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
    textEl.textContent = String(item.text || "").slice(0, MAX_LEN);
    setSource(item.source || "");
    if (caretEl) caretEl.classList.add("is-done");
  }

  /* 打字：用 setTimeout 递归而不是 setInterval，
     这样每步可以带一点随机抖动，停顿更像自然书写 */
  let typeTimer = 0;
  function typeOut(item) {
    const chars = Array.from(String(item.text || "").slice(0, MAX_LEN));
    setSource(item.source || "");
    if (caretEl) caretEl.classList.remove("is-done");

    if (!chars.length) {
      textEl.textContent = FALLBACK;
      if (caretEl) caretEl.classList.add("is-done");
      return;
    }

    let i = 0;
    textEl.textContent = "";

    const step = () => {
      // 一次打 1 个字符；标点后稍作停顿，读起来有呼吸
      textEl.textContent += chars[i];
      const ch = chars[i];
      i += 1;

      if (i >= chars.length) {
        if (caretEl) caretEl.classList.add("is-done");
        typeTimer = 0;
        return;
      }

      let delay = 1000 / CHARS_PER_SEC;
      delay *= 0.72 + Math.random() * 0.56;                 // 抖动
      if ("，。！？；：、,.!?;:".includes(ch)) delay += 150;  // 标点后停顿
      typeTimer = setTimeout(step, delay);
    };

    typeTimer = setTimeout(step, 220);   // 起手稍等一下，让视线落下来
  }

  /* ---------- 抽签 ---------- */

  function pick(list) {
    if (list.length === 1) return list[0];
    let seen = "";
    try { seen = localStorage.getItem(SEEN_KEY) || ""; } catch (e) { /* 隐私模式 */ }

    // 最多试 8 次避开上一句；句库很小时允许重复
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

  /* ---------- 取数 ---------- */

  async function load() {
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 8000) : null;

    try {
      const res = await fetch("/nav.json", {
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (!data || !Array.isArray(data.quotes)) {
        throw new Error("数据里缺少 quotes 数组");
      }

      // 过滤掉空条目（data/quotes.yaml 里可能留了空占位）
      const list = data.quotes
        .map((q) => ({ text: String(q.text || "").trim(), source: String(q.source || "").trim() }))
        .filter((q) => q.text);

      if (!list.length) {
        // empty：句子库是空的 —— 保留兜底句，不显示空白
        console.warn("[quotes] data/quotes.yaml 里还没有句子，显示兜底文案。");
        showFull({ text: FALLBACK, source: "" });
        return;
      }

      const item = pick(list);
      if (reduceMotion) showFull(item);
      else typeOut(item);
    } catch (error) {
      // error：不打扰访客，保留页面上已有的那句，只在控制台留下原因
      const reason = error && error.name === "AbortError"
        ? "请求超时（8 秒）" : String(error && error.message || error);
      console.warn(`[quotes] 句子加载失败（${reason}），保留页面上的兜底文案。`);
      if (caretEl) caretEl.classList.add("is-done");
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  // 页面切走时停掉打字，避免回来接着打
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && typeTimer) {
      clearTimeout(typeTimer);
      typeTimer = 0;
    }
  });

  load();
})();
