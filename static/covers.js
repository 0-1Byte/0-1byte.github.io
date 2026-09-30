/* ==========================================================================
   合集页封面图辅助 — book / docu / film / tv 共用
   Music 页结构不同（正方形封面、独立脚本），未使用本文件。

   做三件事：
     1. srcset/sizes —— 让浏览器按屏幕宽度与 DPR 自己挑尺寸，
        移动端不再下载桌面端的大图
     2. 首屏优先 —— 前 N 张 eager + fetchpriority=high，其余懒加载
     3. 失败兜底 —— WebP 取不到时退回该条目的原始图片

   用法：
     const image = buildCoverImg({
       cover: item.cover,        // 原始 cover 字段（兜底 + 无衍生图时直接用）
       img: item.img,            // 衍生图主干名（由 tools/optimize_covers.py 写入）
       alt: title,
       index: i,
       eagerCount: 4
     });
   依赖 window.COVER_OPT = { widths, sizes }（由页面脚本先设置）。
   ========================================================================== */
(() => {
  "use strict";

  /* 从 /book/ 、/docu/ 这类路径推出站点内该页面的前缀 */
  const BASE = (() => {
    const parts = window.location.pathname.split("/").filter(Boolean);
    return parts.length ? `/${parts[0]}/` : "/";
  })();

  const resolveAsset = path => {
    if (!path) return "";
    if (/^(https?:)?\/\//.test(path) || path.startsWith("/")) return path;
    return BASE + path.replace(/^\.?\//, "");
  };

  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));

  /* 远程封面（第三方 CDN）没有本地衍生图，直接原样加载 */
  const isRemote = path => /^(https?:)?\/\//.test(path || "");

  window.buildCoverImg = function buildCoverImg(options) {
    const opt = window.COVER_OPT || {};
    const widths = opt.widths || [240, 320, 480];
    /* 合集页封面 2:3 竖版，桌面四列时显示约 235x353 */
    const sizes = opt.sizes || "(max-width: 600px) 45vw, (max-width: 850px) 31vw, 235px";

    const index = options.index || 0;
    const eager = index < (options.eagerCount ?? 4);
    const loading = eager
      ? 'loading="eager" fetchpriority="high"'
      : 'loading="lazy"';

    const fallback = resolveAsset(options.cover);
    const base = String(options.img ?? "").trim();
    const alt = escape(options.alt);
    /* 额外属性：传 { name: value } 形式，例如 book 页的 data-fallback */
    const extra = Object.entries(options.extraAttrs || {})
      .filter(([, v]) => v)
      .map(([k, v]) => `${k}="${escape(v)}"`)
      .join(" ");

    /* 没有衍生图信息（远程封面或数据尚未优化）：直接用原图，行为与旧版一致 */
    if (!base || isRemote(options.cover)) {
      return `<img class="cover" src="${escape(fallback)}" alt="${alt}" ${loading} decoding="async"${extra ? ` ${extra}` : ""}>`;
    }

    const dir = opt.assetDir || "covers/opt";
    const srcset = widths
      .map(w => `${BASE}${dir}/${base}-${w}.webp ${w}w`)
      .join(", ");

    return `<img
          class="cover"
          src="${escape(`${BASE}${dir}/${base}-480.webp`)}"
          srcset="${escape(srcset)}"
          sizes="${escape(sizes)}"
          alt="${alt}"
          data-jpg="${escape(fallback)}"
          ${loading}
          decoding="async"${extra ? ` ${extra}` : ""}
        >`;
  };

  /* WebP 加载失败时退回原始图片。必须在页面自己的 error 处理之前拦截，
     并且不能占用 dataset.fallbackTried —— 那是"联网找替代封面"用的，
     这里只是退回本地原图，失败后仍应允许继续走那条逻辑。 */
  window.bindCoverJpgFallback = function bindCoverJpgFallback(root) {
    (root || document).querySelectorAll("img.cover[data-jpg]").forEach(img => {
      img.addEventListener("error", () => {
        const jpg = img.getAttribute("data-jpg");
        if (!jpg || img.dataset.jpgUsed) return;
        img.dataset.jpgUsed = "1";
        img.removeAttribute("srcset");
        img.removeAttribute("sizes");
        img.src = jpg;
      });
    });
  };

  /* 找不到衍生图时的占位：封面文件名派生，避免出现破图（book 页使用） */
  window.COVER_BASE = BASE;
  window.resolveCoverAsset = resolveAsset;
})();
