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

  /* ------------------------------------------------------------------
     下拉菜单的移动端定位

     为什么需要 JS：
       下拉是 position: absolute，而移动端它有两个会把它裁掉的父级 ——
         · .hnav 在窄屏曾是横向滚动容器（overflow-x: auto 会把
           overflow-y 也算成 auto）
         · .header 是 68px 定高
       所以窄屏改用 position: fixed（在 CSS 里由 .hnav-menu--sheet 触发），
       位置在这里按触发按钮的实际位置算出来。
       桌面端维持纯 CSS 的绝对定位，不经过这里。
     ------------------------------------------------------------------ */

  const MOBILE_QUERY = "(max-width: 600px)";
  const VIEWPORT_MARGIN = 12;   // 菜单与视口边缘的最小距离

  function isNarrow() {
    return typeof window.matchMedia === "function"
      && window.matchMedia(MOBILE_QUERY).matches;
  }

  function positionSheet(btn, menu) {
    const rect = btn.getBoundingClientRect();
    const width = Math.min(260, window.innerWidth - VIEWPORT_MARGIN * 2);

    // 左对齐到按钮，但不越出视口
    let left = rect.left;
    if (left + width > window.innerWidth - VIEWPORT_MARGIN) {
      left = window.innerWidth - VIEWPORT_MARGIN - width;
    }
    if (left < VIEWPORT_MARGIN) left = VIEWPORT_MARGIN;

    // 高度自适应，但不超过剩余视口
    const top = rect.bottom + 6;
    const available = window.innerHeight - top - VIEWPORT_MARGIN;

    menu.style.left = `${Math.round(left)}px`;
    menu.style.top = `${Math.round(top)}px`;
    menu.style.width = `${Math.round(width)}px`;
    menu.style.maxHeight = `${Math.max(80, Math.round(available))}px`;
  }

  function clearSheet(menu) {
    menu.classList.remove("hnav-menu--sheet");
    menu.style.left = "";
    menu.style.top = "";
    menu.style.width = "";
    menu.style.maxHeight = "";
  }

  function closeAll(host) {
    host.querySelectorAll(".hnav-item.is-open").forEach(item => {
      item.classList.remove("is-open");
      const b = item.querySelector(".hnav-link--toggle");
      if (b) b.setAttribute("aria-expanded", "false");
      const m = item.querySelector(".hnav-menu");
      if (m) clearSheet(m);
    });
  }

  /* 事件目标是否属于导航。
     注意要单独看 --sheet：移动端菜单是 position: fixed，
     虽然 DOM 上仍在 host 里，但为了不依赖这一点，
     这里显式把它算作「内部」，避免点菜单项时先被判定为外部而收起。 */
  function isInsideNav(host, target) {
    if (!target) return false;
    if (host.contains(target)) return true;
    return !!(target.closest && target.closest(".hnav-menu--sheet"));
  }

  /* 下拉：桌面悬停由 CSS 负责，这里处理点击/键盘（移动端主要靠它） */
  function bindToggles(host) {
    host.querySelectorAll(".hnav-link--toggle").forEach(btn => {
      const item = btn.closest(".hnav-item");
      const menu = item.querySelector(".hnav-menu");

      const setOpen = open => {
        item.classList.toggle("is-open", open);
        btn.setAttribute("aria-expanded", String(open));
        if (!menu) return;
        if (open && isNarrow()) {
          // 先加 class 让 CSS 的 fixed 定位生效，再量位置
          menu.classList.add("hnav-menu--sheet");
          positionSheet(btn, menu);
        } else if (!open) {
          clearSheet(menu);
        }
      };

      btn.addEventListener("click", event => {
        event.preventDefault();
        setOpen(!item.classList.contains("is-open"));
      });

      item.addEventListener("keydown", event => {
        if (event.key === "Escape") {
          setOpen(false);
          btn.focus();
        }
      });

      // 焦点离开整组时收起，避免键盘用户被困在展开态
      item.addEventListener("focusout", event => {
        if (!item.contains(event.relatedTarget)) setOpen(false);
      });

      // 展开状态下视口变化（旋转屏幕、软键盘弹出）需要重算位置
      window.addEventListener("resize", () => {
        if (item.classList.contains("is-open") && menu && isNarrow()) {
          positionSheet(btn, menu);
        }
      }, { passive: true });

      // 从窗口宽度看，要跨过 600px 时把 sheet 状态清掉，
      // 否则桌面端会残留 fixed 定位
      if (typeof window.matchMedia === "function") {
        const mq = window.matchMedia(MOBILE_QUERY);
        const onChange = () => {
          if (!mq.matches) setOpen(false);
        };
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
      }
    });

    // 点击别处收起
    document.addEventListener("click", event => {
      if (!isInsideNav(host, event.target)) closeAll(host);
    });

    // 滚动时收起：fixed 定位不跟随页面滚动，留着会飘在错误的位置
    // （菜单自身内部的滚动也会冒泡到 window，所以先判断目标是否在菜单里）
    window.addEventListener("scroll", event => {
      if (isInsideNav(host, event.target)) return;
      closeAll(host);
    }, { passive: true, capture: true });
  }

  /* ------------------------------------------------------------------
     主题：本脚本不再处理

     这里原先有一整套「主题切换」绑定（直接绑定 + 捕获委托 + 时间戳去重），
     是前几轮反复修「点了没反应」留下的。现在主题切换按钮已从所有页面移除，
     全站固定深色（见 extend_head.html 与各合集页 <head>），
     那套逻辑永远找不到 #theme-toggle，成了死代码。

     按「不顺手重构」的要求，这里只删掉确实不再被需要的部分，
     并留下这段说明，避免以后有人以为按钮是被漏掉的。
     ------------------------------------------------------------------ */

  /* 保留 storage 同步：同一浏览器多标签时，
     若将来重新加回主题切换，这个键的语义仍然一致。
     现在它只会在别的标签写入 pref-theme 时跟随，不主动改主题。 */
  window.addEventListener("storage", event => {
    if (event.key === "pref-theme"
      && (event.newValue === "light" || event.newValue === "dark")) {
      document.documentElement.dataset.theme = event.newValue;
    }
  });

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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadAndRender, { once: true });
  } else {
    loadAndRender();
  }
})();
