/* ==========================================================================
   合集页共用的「加载状态 / 失败诊断」— 七个页面（music/book/works/docu/film/tv/game）
   都引用本文件。

   为什么要共用：
     7 个页面各自有一份 script.js，但加载状态与失败提示必须完全一致。
     各写一份必然漂移，所以收敛到这里。

   提供三个能力：
     window.derivePageBase(scriptUrl)  从脚本自身 URL 推出该页目录（子目录部署安全）
     window.setCollectionLoading(el, label)   首屏 loading 占位
     window.showCollectionError(el, info)     失败时显示：请求 URL + 失败原因 + 建议

   注意：不依赖任何框架，纯原生 DOM。
   ========================================================================== */
(() => {
  "use strict";

  /* ---------- 页面前缀推导 ----------
     用脚本自身的 URL（script 标签的 src 会按文档地址解析成绝对 URL）反推目录，
     这样无论部署在 origin 根还是 /sub/ 子目录，也不受"当前文档路径"写法影响。
     例：https://host/music/script.js      -> /music/
         https://host/sub/music/script.js  -> /sub/music/  */
  window.derivePageBase = function derivePageBase(scriptUrl) {
    try {
      const url = new URL(scriptUrl, document.baseURI);
      return url.pathname.replace(/[^/]*$/, "");   // 去掉文件名，保留目录
    } catch (error) {
      console.warn("[collection] 无法从脚本 URL 推导目录，退回根路径：", error);
      return "/";
    }
  };

  /* ---------- loading 占位 ---------- */
  window.setCollectionLoading = function setCollectionLoading(el, label) {
    if (!el) return;
    el.hidden = false;
    el.dataset.state = "loading";
    el.innerHTML = `<span class="state-spinner" aria-hidden="true"></span>`
      + `<span>正在加载${label ? " " + escapeText(label) : ""}…</span>`;
  };

  /* ---------- 失败诊断 ----------
     info = { url, reason, detail, kind }
       kind: "network" | "http" | "data" | "unknown"  —— 决定给什么排查建议 */
  window.showCollectionError = function showCollectionError(el, info) {
    if (!el) return;
    const diagnosis = describeFailure(info);
    el.hidden = false;
    el.dataset.state = "error";
    el.innerHTML = `
      <p class="state-title">${escapeText(diagnosis.title)}</p>
      ${info.url ? `<p class="state-row"><span class="state-label">请求地址</span><code>${escapeText(info.url)}</code></p>` : ""}
      ${info.reason ? `<p class="state-row"><span class="state-label">失败原因</span><span>${escapeText(info.reason)}</span></p>` : ""}
      ${info.detail ? `<p class="state-row"><span class="state-label">详细信息</span><span>${escapeText(info.detail)}</span></p>` : ""}
      <p class="state-row"><span class="state-label">建议</span><span>${escapeText(diagnosis.hint)}</span></p>
    `;
    // 同时在 console 留下完整现场，方便排查
    console.error(`[collection] 数据加载失败\n  请求地址: ${info.url}\n  失败原因: ${info.reason}\n  详细信息: ${info.detail || "-"}`);
  };

  function describeFailure(info) {
    switch (info.kind) {
      case "network":
        return {
          title: "数据请求失败",
          hint: "网络不可用、请求被拦截或文件路径不对。确认该 JSON 文件已随站点部署，并检查是否有离线/代理拦截。"
        };
      case "http":
        return {
          title: "服务器返回错误",
          hint: "文件可能不存在或路径不对。确认该 JSON 位于对应目录下，且已包含在部署产物中。"
        };
      case "data":
        return {
          title: "数据格式异常",
          hint: "文件取到了，但不是预期的 JSON 数组。用 JSON 校验工具检查该文件是否被破坏。"
        };
      default:
        return {
          title: "数据加载失败", hint: "请打开浏览器控制台查看完整错误堆栈。"
        };
    }
  }

  /* 把 fetch 的各种失败归类，便于给出可操作的提示 */
  window.classifyLoadError = function classifyLoadError(error, response) {
    if (response && !response.ok) {
      return { kind: "http", reason: `HTTP ${response.status} ${response.statusText || ""}`.trim() };
    }
    if (error && error.name === "AbortError") {
      return { kind: "network", reason: "请求超时（超过 10 秒无响应）" };
    }
    if (error instanceof SyntaxError) {
      return { kind: "data", reason: "JSON 解析失败", detail: error.message };
    }
    if (error) {
      return { kind: "network", reason: error.message || String(error), detail: error.name };
    }
    return { kind: "unknown", reason: "未知错误" };
  };

  function escapeText(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[char]));
  }

  /* ---------- 带超时的 JSON 读取 ----------
     统一入口，避免每个页面各写一遍 fetch + 超时 + 错误归类 */
  window.fetchCollectionJson = async function fetchCollectionJson(url, options) {
    const opt = options || {};
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(), opt.timeout || 10000)
      : null;
    let response = null;
    try {
      response = await fetch(url, {
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined
      });
      if (!response.ok) {
        return { ok: false, ...window.classifyLoadError(null, response), url };
      }
      const data = await response.json();
      return { ok: true, data, url };
    } catch (error) {
      return { ok: false, ...window.classifyLoadError(error, null), url };
    } finally {
      if (timer) clearTimeout(timer);
    }
  };
})();
