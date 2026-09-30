/* ==========================================================================
   回到顶部按钮 — 行为层（全站共用）
   · 若页面已有 PaperMod 的 #top-link：直接复用它，只补上图标与进度环
   · 若页面没有（static/ 下的独立合集页）：现场创建一个
   · 滚动超过一屏后淡入；点击平滑回顶；进度环跟随阅读位置
   配套样式见 /back-to-top.css
   ========================================================================== */
(() => {
  "use strict";

  const READY = () => {
    /* ---------- 1. 找到或创建按钮 ---------- */
    let link = document.getElementById("top-link");

    if (!link) {
      link = document.createElement("a");
      link.className = "top-link hidden";
      link.setAttribute("id", "top-link");
      link.setAttribute("href", "#top");
      link.setAttribute("accesskey", "g");
      document.body.appendChild(link);
    }

    link.setAttribute("aria-label", "回到顶部");
    link.setAttribute("title", "回到顶部 (Alt + G)");

    /* ---------- 2. 图标 ----------
       PaperMod 自带的是一枚双箭头 svg，.top-link 里只应有一个图标：
       先把非进度环的 svg 全部清掉，再补上我们自己的单箭头。
       否则会和主题图标叠在一起（两个箭头压在同一位置上）。 */
    let arrow = link.querySelector("svg.top-link-arrow");

    if (!arrow) {
      link.querySelectorAll("svg").forEach(svg => {
        if (!svg.classList.contains("top-link-ring")) svg.remove();
      });

      arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      arrow.setAttribute("class", "top-link-arrow");
      arrow.setAttribute("viewBox", "0 0 24 24");
      arrow.setAttribute("aria-hidden", "true");
      arrow.setAttribute("fill", "none");
      arrow.setAttribute("stroke", "currentColor");
      arrow.setAttribute("stroke-width", "2");
      arrow.setAttribute("stroke-linecap", "round");
      arrow.setAttribute("stroke-linejoin", "round");
      arrow.innerHTML = '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>';
      link.appendChild(arrow);
    }

    /* ---------- 3. 进度环 ---------- */
    const RADIUS = 20;
    const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
    let bar = link.querySelector(".tt-bar");

    if (!bar) {
      const ring = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      ring.setAttribute("class", "top-link-ring");
      ring.setAttribute("viewBox", "0 0 44 44");
      ring.setAttribute("aria-hidden", "true");
      ring.setAttribute("focusable", "false");

      const track = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      track.setAttribute("class", "tt-track");
      track.setAttribute("cx", "22");
      track.setAttribute("cy", "22");
      track.setAttribute("r", String(RADIUS));

      bar = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      bar.setAttribute("class", "tt-bar");
      bar.setAttribute("cx", "22");
      bar.setAttribute("cy", "22");
      bar.setAttribute("r", String(RADIUS));
      bar.setAttribute("stroke-dasharray", String(CIRCUMFERENCE));
      bar.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE));

      ring.appendChild(track);
      ring.appendChild(bar);
      link.appendChild(ring);
    }

    /* ---------- 4. 滚动状态 ---------- */
    const scrollElement = document.documentElement;
    let isHidden = link.classList.contains("hidden");

    const setRing = () => {
      const scrollable = scrollElement.scrollHeight - window.innerHeight;
      const progress = scrollable > 0
        ? Math.min(1, Math.max(0, scrollElement.scrollTop / scrollable))
        : 0;
      bar.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - progress));
    };

    /* PaperMod 自带一段 window.onscroll 负责显隐，这里只负责进度环，
       显隐交给下面的 update()，两者不冲突。 */
    const update = () => {
      const past = (window.scrollY || scrollElement.scrollTop || 0) > window.innerHeight * 0.8;

      if (past === isHidden) {
        isHidden = !past;
        link.classList.toggle("hidden", !past);
      }

      /* 首次出现时才计算一次，避免在顶部写入无意义的 offset */
      if (past) setRing();
    };

    let scheduled = false;
    const onScroll = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        update();
      });
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    /* ---------- 5. 点击回顶 ---------- */
    link.addEventListener("click", event => {
      event.preventDefault();
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
      if (history.replaceState) history.replaceState(null, "", window.location.pathname + window.location.search);
    });

    update();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", READY, { once: true });
  } else {
    READY();
  }
})();
