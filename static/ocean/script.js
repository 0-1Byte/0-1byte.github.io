/* ==========================================================================
   /ocean/ —— 程序化海面（WebGL）

   为什么用 shader 而不是图片：
     一张「真实、安静、深蓝」的海面如果是位图，要么体积很大，
     要么一眼看出是贴图在平移。程序化海面能同时做到体积小、
     分辨率无关、且波纹永远不重复。

   视觉目标（严格对照阶段要求）：
     ✓ 深蓝、低饱和
     ✓ 清晰但柔和的 horizon
     ✓ 非常细小的波澜
     ✓ 远处轻微雾气
     ✓ 大量留白（天空占比大）
     ✓ 极少量动态：大尺度缓慢起伏 + 小尺度不规则波纹
     ✗ 不做卡通海面 / 低模海洋 / 蓝色渐变背景 / 网格波浪 / 游戏场景

   动画速度刻意压到极低：
     最大的一组涌浪周期约 130 秒，振幅约 1.5px —— 看 10 秒几乎察觉不到，
     几十秒后才会隐约觉得海面「在呼吸」。

   失败处理：任何一步出错都不留白屏 ——
     画布保持透明，露出下层 .ocean-fallback 的静态 CSS 海面，
     并在 console 留下原因，页面底部给出极小的一行说明。
   ========================================================================== */
(() => {
  "use strict";

  const canvas = document.getElementById("ocean");
  const noteEl = document.getElementById("ocean-note");
  const linksEl = document.getElementById("ocean-links");
  const reduceMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function showNote(html) {
    if (!noteEl) return;
    noteEl.innerHTML = html;
    noteEl.hidden = false;
  }

  /* ---------------------------------------------------------------
     一、着色器
     --------------------------------------------------------------- */

  const VERT = `
attribute vec2 aPos;
void main() {
  gl_Position = vec4(aPos, 0.0, 1.0);
}`;

  const FRAG = `
precision highp float;

uniform vec2  uRes;
uniform float uTime;
uniform float uHorizon;

/* ---- 值噪声：三次平滑插值，得到无方向性的柔和斑块 ---- */
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

/* ---- 一维起伏：叠两个倍频程，得到「大尺度缓慢 + 小尺度不规则」 ---- */
float swell(float x, float t) {
  float a = sin(x * 0.90 + t * 0.21);
  float b = sin(x * 2.30 - t * 0.37 + 1.7);
  return a * 0.62 + b * 0.38;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float aspect = uRes.x / uRes.y;

  /* 把 x 轴归一化到 0..1，避免宽屏上波纹被横向拉伸 */
  float nx = (uv.x - 0.5) * aspect;

  float d = uv.y - uHorizon;          // > 0 海面，< 0 天空
  float sea = smoothstep(-0.0035, 0.0035, d);

  /* ---------- 海面 ---------- */

  /* 从地平线向下做透视压缩：越近处，同一屏幕距离代表的实际距离越大。
     这比「逐行平移噪声」更接近真实海面的观感。 */
  float depth = (uv.y - uHorizon) / max(1.0 - uHorizon, 1e-4);
  depth = clamp(depth, 0.0, 1.0);
  float persp = 1.0 / (depth * 7.0 + 0.06);

  vec2 wp = vec2(nx * persp * 0.85, persp * 0.5);

  /* 两组噪声叠加：一组很慢（长涌），一组稍快（细波）。
     两者的空间尺度也拉开，避免出现规则网格感。 */
  float n1 = noise(wp * 0.50 + vec2(uTime * 0.008, -uTime * 0.005));
  float n2 = noise(wp * 1.70 + vec2(-uTime * 0.014, uTime * 0.019));
  float n3 = noise(wp * 4.20 + vec2(uTime * 0.026, -uTime * 0.031));

  float ripple = n1 * 0.58 + n2 * 0.27 + n3 * 0.15;
  ripple = ripple * 2.0 - 1.0;

  /* 垂直方向的细微波浪 —— 这是最关键的一层：
     它让「地平线上的起伏」产生，而不是整片海面亮度一起变。
     横向波长与纵向波长不同，避免等距条纹。
     相位里掺入噪声，让波形不规则（否则会出现规则的正弦条纹）。 */
  float phaseA = nx * 3.2 + (hash(floor(wp * 64.0)) - 0.5) * 1.6;
  float wave = swell(phaseA, uTime) * 0.16;
  float crest = swell(nx * 7.5 + 2.1, uTime * 1.4) * 0.07;

  /* 越靠地平线振幅越小（远处更平） */
  float far = 1.0 - smoothstep(0.0, 0.42, depth);
  float amp = mix(0.35, 1.0, far);

  float hl = (wave + crest) * amp;

  /* ---------- 海面颜色 ---------- */

  vec3 seaFar  = vec3(0.400, 0.478, 0.545);
  vec3 seaMid  = vec3(0.100, 0.170, 0.238);
  vec3 seaNear = vec3(0.032, 0.062, 0.098);

  vec3 col = mix(seaFar, seaMid, smoothstep(0.0, 0.30, depth));
  col = mix(col, seaNear, smoothstep(0.26, 1.0, depth));

  /* 波纹只做极轻微的明暗，不做白色浪花 */
  col += ripple * 0.030 * mix(0.45, 1.0, depth);

  /* 由起伏带来的高光：集中在海平线附近，像远处被雾散开的反光 */
  col += max(hl, 0.0) * 0.30 * exp(-depth * 3.4);

  /* ---------- 天空 ---------- */

  float skyT = clamp(-d / max(uHorizon, 1e-4), 0.0, 1.0);
  vec3 skyHigh = vec3(0.026, 0.056, 0.090);
  vec3 skyMid  = vec3(0.066, 0.108, 0.158);
  vec3 skyLow  = vec3(0.300, 0.360, 0.430);

  vec3 sky = mix(skyLow, skyMid, smoothstep(0.0, 0.42, skyT));
  sky = mix(sky, skyHigh, smoothstep(0.34, 1.0, skyT));

  /* 天空里极淡的云层，横向拉长，避免抢视线 */
  float cloud = noise(vec2(nx * 1.5, skyT * 3.4) + vec2(uTime * 0.0016, 0.0));
  sky += (cloud - 0.5) * 0.035 * smoothstep(0.05, 0.8, skyT);

  /* ---------- 合成 ---------- */

  vec3 finalCol = mix(sky, col, sea);

  /* 海平线上的雾气：把天空与海面柔化地缝在一起 */
  float band = exp(-abs(d) * 34.0);
  finalCol = mix(finalCol, vec3(0.455, 0.520, 0.575), band * 0.55);

  /* 极轻的暗角，视线收到中央 */
  float vig = smoothstep(1.15, 0.25, length((uv - vec2(0.5, 0.46)) * vec2(1.0, 1.1)));
  finalCol *= mix(0.86, 1.0, vig);

  /* 轻微去饱和，避免变成「蓝色渐变背景」 */
  float lum = dot(finalCol, vec3(0.2126, 0.7152, 0.0722));
  finalCol = mix(vec3(lum), finalCol, 0.88);

  gl_FragColor = vec4(finalCol, 1.0);
}`;

  /* ---------------------------------------------------------------
     二、WebGL 初始化（任何一步失败都回退到 CSS 海面）
     --------------------------------------------------------------- */

  function compile(gl, type, source) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, source);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(sh);
      gl.deleteShader(sh);
      throw new Error(`${type === gl.VERTEX_SHADER ? "顶点" : "片元"}着色器编译失败：${info}`);
    }
    return sh;
  }

  function readHorizon() {
    const raw = getComputedStyle(document.documentElement)
      .getPropertyValue("--ocean-horizon").trim();
    const n = parseFloat(raw);
    return Number.isFinite(n) && n > 0 && n < 1 ? n : 0.58;
  }

  let gl = null;
  let program = null;
  let uRes = null;
  let uTime = null;
  let uHorizon = null;

  function initGL() {
    const opts = {
      alpha: false,
      antialias: false,       // 全屏渐变，不需要 MSAA，省一半带宽
      depth: false,
      stencil: false,
      powerPreference: "low-power",
      preserveDrawingBuffer: false
    };
    gl = canvas.getContext("webgl", opts) || canvas.getContext("experimental-webgl", opts);
    if (!gl) throw new Error("浏览器未提供 WebGL 上下文");

    program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`着色器链接失败：${gl.getProgramInfoLog(program)}`);
    }
    gl.useProgram(program);

    // 全屏三角形（比两个三角形少一个顶点的插值边界）
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1, -1, 3, -1, -1, 3
    ]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(program, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    uRes = gl.getUniformLocation(program, "uRes");
    uTime = gl.getUniformLocation(program, "uTime");
    uHorizon = gl.getUniformLocation(program, "uHorizon");
  }

  function resize() {
    if (!gl) return;
    // 程序化渐变不需要全分辨率；限制像素比可以显著降低移动端功耗
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  function draw(seconds) {
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, seconds);
    gl.uniform1f(uHorizon, readHorizon());
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  let rafId = 0;
  let start = 0;

  function loop(now) {
    if (!start) start = now;
    // 时间单位取「秒」，但整体速度在 shader 里已经压得很低
    draw((now - start) * 0.001);
    rafId = requestAnimationFrame(loop);
  }

  function bootGL() {
    try {
      initGL();
    } catch (error) {
      // 回退：画布保持透明 → 露出 .ocean-fallback
      canvas.style.display = "none";
      console.error("[ocean] WebGL 初始化失败，已回退到静态海面：", error);
      showNote(`海面以静态方式呈现（<code>${String(error.message || error).slice(0, 90)}</code>）`);
      return false;
    }

    resize();
    window.addEventListener("resize", resize, { passive: true });

    if (reduceMotion) {
      // 用户要求减少动效：只画一帧静止的海面
      draw(42.0);
      return true;
    }

    rafId = requestAnimationFrame(loop);

    // 切到后台时停掉渲染，回来再续上 —— 不浪费电
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      } else if (!rafId) {
        rafId = requestAnimationFrame(loop);
      }
    });
    return true;
  }

  /* ---------------------------------------------------------------
     三、底部入口：从 /nav.json 取，与全站信息架构同源
     --------------------------------------------------------------- */

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  async function loadLinks() {
    if (!linksEl) return;
    linksEl.classList.add("is-loading");

    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 8000) : null;

    try {
      const res = await fetch("/nav.json", {
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const nav = await res.json();
      if (!nav || !Array.isArray(nav.groups)) throw new Error("nav.json 格式不对（缺少 groups 数组）");

      const entries = [];
      nav.groups
        .filter((g) => !g.pending && Array.isArray(g.children) && g.children.length)
        .forEach((g) => entries.push({ name: g.label, href: g.children[0].href }));
      (nav.standalone || []).forEach((s) => entries.push({ name: s.name, href: s.href }));

      if (!entries.length) {
        linksEl.classList.remove("is-loading");
        showNote("没有可用的分区入口。");
        return;
      }

      linksEl.innerHTML = entries.map((e) =>
        `<a href="${esc(e.href)}">${esc(e.name)}</a>`).join("");
      linksEl.classList.remove("is-loading");
    } catch (error) {
      linksEl.classList.remove("is-loading");
      const reason = error && error.name === "AbortError" ? "请求超时（8 秒）" : String(error && error.message || error);
      console.error("[ocean] 分区入口加载失败：", error);
      showNote(`分区入口加载失败：<code>${esc(reason)}</code>`);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  /* ---------------------------------------------------------------
     四、启动
     --------------------------------------------------------------- */

  if (canvas) bootGL();
  else showNote("找不到海面画布。");

  loadLinks();
})();
