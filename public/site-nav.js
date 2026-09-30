/* ==========================================================================
   全站导航 —— 客户端渲染版
   服务 static/ 下的合集页（首页/文章页由 Hugo 的 site_nav.html 服务端渲染）。

   数据来源：/nav.json —— 由 Hugo 从 data/nav.yaml 生成
   （layouts/index.json + hugo.toml 的 NavIndex 输出格式）。
   之所以用文件而不是内联注入：static/ 下的页面是原样复制的静态文件，
   不经过 Hugo 模板，内联注入对它们无效。
   两侧因此始终来自同一份配置，不会漂移。

   渲染出的 class 结构与 site_nav.html 完全一致（hnav-*），
   样式来自 /site-nav.css，两种页面外观一致。

   同时负责：移动端下拉展开、键盘可用性、当前页高亮、主题切换。
   ========================================================================== */
(() => {
  "use strict";

  const NAV_URL = "/nav.json";

  const current = () => window.location.pathname.replace(/index\.html$/, "");

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  function isActive(href) {
    const here = current();
    const target = href.replace(/index\.html$/, "");
    return target !== "/" && here.startsWith(target);
  }

  function buildGroup(group) {
    const children = group.children || [];
    const multi = children.length > 1;
    const active = children.some(c => isActive(c.href));

    if (multi) {
      const items = children.map(c => `
          <li>
            <a href="${esc(c.href)}"${isActive(c.href) ? ' class="is-active"' : ""}>
              <span class="hnav-menu-name">${esc(c.name)}</span>
              ${c.desc ? `<span class="hnav-menu-desc">${esc(c.desc)}</span>` : ""}
            </a>
          </li>`).join("");
      return `
      <li class="hnav-item hnav-item--has-menu${active ? " is-active" : ""}" data-group="${esc(group.key)}">
        <button class="hnav-link hnav-link--toggle" type="button" aria-expanded="false" aria-haspopup="true">
          <span>${esc(group.label)}</span>
          <svg class="hnav-caret" viewBox="0 0 24 24" width="10" height="10" fill="none"
               stroke="currentColor" stroke-width="2.4" stroke-linecap="round"
               stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <ul class="hnav-menu">${items}</ul>
      </li>`;
    }

    const only = children[0];
    return `
      <li class="hnav-item${active ? " is-active" : ""}" data-group="${esc(group.key)}">
        <a class="hnav-link" href="${esc(only.href)}" title="${esc(only.desc || only.name)}">
          <span>${esc(group.label)}</span>
        </a>
      </li>`;
  }

  function render(nav) {
    const host = document.querySelector("[data-site-nav]");
    if (!host) {
      console.error("[site-nav] 找不到 [data-site-nav] 容器，导航未渲染。");
      return;
    }
    const groups = (nav.groups || []).filter(g => !g.pending);
    const standalone = nav.standalone || [];
    const standaloneHtml = standalone.map(s => `
      <li class="hnav-item">
        <a class="hnav-link" href="${esc(s.href)}" title="${esc(s.desc || s.name)}">
          <span>${esc(s.name)}</span>
        </a>
      </li>`).join("");
    host.innerHTML = `<ul class="hnav-list">${groups.map(buildGroup).join("")}${standaloneHtml}</ul>`;
    host.classList.add("hnav");
    bindToggles(host);
  }

  /* 数据缺失时不静默：把原因写进容器，避免用户看到一个"空导航"却不知为何 */
  function renderNavError(host, reason) {
    if (!host) return;
    host.innerHTML = `<span class="hnav-error">导航数据加载失败：${esc(reason)}</span>`;
    console.error(`[site-nav] 无法加载 ${NAV_URL} —— ${reason}`);
  }

  /* 下拉：桌面悬停由 CSS 负责，这里处理点击/键盘（移动端主要靠它） */
  function bindToggles(host) {
    host.querySelectorAll(".hnav-link--toggle").forEach(btn => {
      const item = btn.closest(".hnav-item");

      btn.addEventListener("click", event => {
        event.preventDefault();
        const open = item.classList.toggle("is-open");
        btn.setAttribute("aria-expanded", String(open));
      });

      item.addEventListener("keydown", event => {
        if (event.key === "Escape") {
          item.classList.remove("is-open");
          btn.setAttribute("aria-expanded", "false");
          btn.focus();
        }
      });

      // 焦点离开整组时收起，避免键盘用户被困在展开态
      item.addEventListener("focusout", event => {
        if (!item.contains(event.relatedTarget)) {
          item.classList.remove("is-open");
          btn.setAttribute("aria-expanded", "false");
        }
      });
    });

    // 点击别处收起
    document.addEventListener("click", event => {
      if (!host.contains(event.target)) {
        host.querySelectorAll(".hnav-item.is-open").forEach(i => {
          i.classList.remove("is-open");
          const b = i.querySelector(".hnav-link--toggle");
          if (b) b.setAttribute("aria-expanded", "false");
        });
      }
    });
  }

  /* ------------------------------------------------------------------
     主题切换

     这里同时装两道保险，因为"点了没反应"可能来自两个完全不同的原因：

       a) 没有绑定成功
          → 用 DOM 归属判断：Hugo 页面的按钮固定在 .logo-switches 内，
            PaperMod 页脚已经绑好，本脚本跳过；合集页没有这层，由本脚本负责。

       b) 绑定成功了，但点击被别的东西挡掉
          （导航会 flex 伸展、下拉菜单有层级、绝对定位元素可能叠在按钮上）
          → 用「捕获阶段的事件委托」直接挂在 document 上：
            捕获阶段先于任何冒泡处理器执行，也不受目标元素被遮挡的影响，
            只要事件落在按钮或其内部（svg 图标）就能命中。

     两者用 event.__snavToggle 标记互斥：
       · 委托先跑  → 打标记，直接绑定不再切换
       · 直接绑定先跑 → 打标记，委托跳过
     所以不会出现"切两次又切回来"。
     ------------------------------------------------------------------ */
  const THEME_FLAG = "__snavToggleHandled";

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("pref-theme", next);
    } catch (error) {
      console.warn("[site-nav] 无法写入 localStorage，主题偏好不会被记住：", error);
    }
  }

  function handleToggleClick(event) {
    if (event[THEME_FLAG]) return;
    event[THEME_FLAG] = true;
    toggleTheme();
  }

  function bindThemeToggle() {
    const button = document.getElementById("theme-toggle");
    if (!button) return;

    // 1) 页面自带实现：合集页在 <head> 内联了主题切换，
    //    按钮带 data-theme-owner="page" 标记 —— 这里必须完全不插手，
    //    否则同一个按钮会被处理两次（切过去又切回来）。
    if (button.dataset.themeOwner === "page") return;

    // 2) Hugo 页面由 PaperMod 页脚绑定（按钮固定放在 .logo-switches 内）
    if (button.closest(".logo-switches")) return;

    // 3) 幂等：本脚本被重复执行时不重复绑定
    if (button.dataset.snavBound === "1") return;
    button.dataset.snavBound = "1";

    button.addEventListener("click", handleToggleClick);
    button.addEventListener("click", handleToggleClick, true);

    window.addEventListener("storage", event => {
      if (event.key === "pref-theme"
        && (event.newValue === "light" || event.newValue === "dark")) {
        document.documentElement.dataset.theme = event.newValue;
      }
    });
  }

  /* 拉取导航数据并渲染。带超时，失败时明确提示而不是留一个空导航。 */
  async function loadAndRender() {
    const host = document.querySelector("[data-site-nav]");
    if (!host) {
      console.error("[site-nav] 找不到 [data-site-nav] 容器，导航未渲染。");
      return;
    }

    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 8000) : null;

    try {
      const res = await fetch(NAV_URL, {
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined
      });
      if (!res.ok) {
        renderNavError(host, `HTTP ${res.status}`);
        return;
      }
      const nav = await res.json();
      if (!nav || !Array.isArray(nav.groups)) {
        renderNavError(host, "nav.json 格式不对（缺少 groups 数组）");
        return;
      }
      render(nav);
    } catch (error) {
      renderNavError(host, error && error.name === "AbortError" ? "请求超时" : String(error));
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  /* 先绑主题按钮，再做任何异步工作 ——
     这样即使 /nav.json 拉取失败或超时，主题切换依然可用。 */
  function boot() {
    bindThemeToggle();
    loadAndRender();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
