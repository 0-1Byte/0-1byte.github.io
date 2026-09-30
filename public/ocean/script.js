/* ==========================================================================
   /ocean/ —— 站在海边，看着远处海平线

   这一页不是「一个导航页」，而是网站的一个隐喻入口：
     · 全屏只有海、天、以及三个字 CHEN
     · 没有卡片，没有按钮堆砌
     · 海面上偶尔出现一个很小的东西（船 / 鸟 / 光 / 浮标 / 星）
       点它，进入对应的分区 —— 网站因此有了一层隐喻

   时间会缓慢变化：白天亮、黄昏金、夜晚深蓝带星光。
   依据是访问者本机时间，跨过整点时会平滑过渡（不是硬切）。

   色板用三段式（白天 / 黄昏 / 夜晚）加权混合，而不是一串 if：
   着色器里不能用动态下标访问数组，所以权重由 JS 算好传进来。

   动效克制：海面 10 秒内变化约 1/255；海面上的东西 40—80 秒一轮
   淡入淡出，任意时刻最多三个可见。

   失败处理：任何一步出错都不留白屏 ——
     画布隐藏，露出 .ocean-fallback 的静态 CSS 海面；
     console 留下原因，角落给一行极小说明。
   ========================================================================== */
(() => {
  "use strict";

  const canvas = document.getElementById("ocean");
  const noteEl = document.getElementById("ocean-note");
  const objectsEl = document.getElementById("ocean-objects");
  const reduceMotion = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // 调试用：?all=1 让所有隐喻同时出现，便于确认它们指向哪里
  const showAll = /[?&]all=1\b/.test(window.location.search);

  function showNote(html) {
    if (!noteEl) return;
    noteEl.innerHTML = html;
    noteEl.hidden = false;
  }

  /* ---------------------------------------------------------------
     一、一天中的色板
     三段：白天 / 黄昏 / 夜晚。用权重混合，跨时段是渐变而不是跳变。
     --------------------------------------------------------------- */

  const PALETTES = {
    day: {
      skyHigh: [0.28, 0.44, 0.60], skyMid: [0.45, 0.60, 0.73], skyLow: [0.72, 0.80, 0.85],
      seaFar: [0.52, 0.62, 0.68], seaMid: [0.20, 0.36, 0.48], seaNear: [0.05, 0.14, 0.24],
      horizon: [0.80, 0.86, 0.90], sway: 0.85
    },
    dusk: {
      skyHigh: [0.16, 0.20, 0.34], skyMid: [0.44, 0.32, 0.38], skyLow: [0.88, 0.62, 0.38],
      seaFar: [0.62, 0.50, 0.44], seaMid: [0.24, 0.22, 0.30], seaNear: [0.06, 0.08, 0.14],
      horizon: [0.95, 0.76, 0.52], sway: 0.70
    },
    night: {
      skyHigh: [0.026, 0.056, 0.090], skyMid: [0.066, 0.108, 0.158], skyLow: [0.180, 0.230, 0.300],
      seaFar: [0.30, 0.38, 0.45], seaMid: [0.070, 0.125, 0.185], seaNear: [0.026, 0.052, 0.084],
      horizon: [0.38, 0.46, 0.54], sway: 1.0
    }
  };

  /* 一天中的关键点 -> 相邻两段色板的混合权重 */
  function phaseWeights(hour) {
    const stops = [0, 4.5, 7, 12, 17, 19.5, 22, 24];
    const keys = ["night", "night", "dusk", "day", "dusk", "dusk", "night", "night"];
    let i = 0;
    while (i < stops.length - 1 && hour >= stops[i + 1]) i++;
    const t = (hour - stops[i]) / Math.max(stops[i + 1] - stops[i], 1e-6);
    const a = keys[i], b = keys[Math.min(i + 1, keys.length - 1)];
    const w = { day: 0, dusk: 0, night: 0 };
    if (a === b) { w[a] = 1; return w; }
    w[a] = 1 - t;
    w[b] += t;
    return w;
  }

  /* 按权重把三段色板混成一个调色板 */
  function blendedPalette(w) {
    const out = {};
    ["skyHigh", "skyMid", "skyLow", "seaFar", "seaMid", "seaNear", "horizon"].forEach((field) => {
      out[field] = [0, 1, 2].map((c) =>
        PALETTES.day[field][c] * w.day
        + PALETTES.dusk[field][c] * w.dusk
        + PALETTES.night[field][c] * w.night);
    });
    out.sway = PALETTES.day.sway * w.day + PALETTES.dusk.sway * w.dusk + PALETTES.night.sway * w.night;
    out.night = w.night;
    return out;
  }

  /* ---------------------------------------------------------------
     二、着色器
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
uniform float uSway;

uniform vec3 uSkyHigh;
uniform vec3 uSkyMid;
uniform vec3 uSkyLow;
uniform vec3 uSeaFar;
uniform vec3 uSeaMid;
uniform vec3 uSeaNear;
uniform vec3 uHorizonCol;
uniform float uStars;

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

float swell(float x, float t) {
  float a = sin(x * 0.90 + t * 0.21);
  float b = sin(x * 2.30 - t * 0.37 + 1.7);
  return a * 0.62 + b * 0.38;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float aspect = uRes.x / uRes.y;
  float nx = (uv.x - 0.5) * aspect;

  float d = uv.y - uHorizon;
  float sea = smoothstep(-0.0035, 0.0035, d);

  /* ---------- 海面 ---------- */

  float depth = (uv.y - uHorizon) / max(1.0 - uHorizon, 1e-4);
  depth = clamp(depth, 0.0, 1.0);
  float persp = 1.0 / (depth * 7.0 + 0.06);

  vec2 wp = vec2(nx * persp * 0.85, persp * 0.5);

  float n1 = noise(wp * 0.50 + vec2(uTime * 0.008, -uTime * 0.005));
  float n2 = noise(wp * 1.70 + vec2(-uTime * 0.014, uTime * 0.019));
  float n3 = noise(wp * 4.20 + vec2(uTime * 0.026, -uTime * 0.031));

  float ripple = (n1 * 0.58 + n2 * 0.27 + n3 * 0.15) * 2.0 - 1.0;

  float phaseA = nx * 3.2 + (hash(floor(wp * 64.0)) - 0.5) * 1.6;
  float wave = swell(phaseA, uTime) * 0.16;
  float crest = swell(nx * 7.5 + 2.1, uTime * 1.4) * 0.07;

  float far = 1.0 - smoothstep(0.0, 0.42, depth);
  float amp = mix(0.35, 1.0, far);
  float hl = (wave + crest) * amp;

  vec3 col = mix(uSeaFar, uSeaMid, smoothstep(0.0, 0.30, depth));
  col = mix(col, uSeaNear, smoothstep(0.26, 1.0, depth));
  col += ripple * 0.030 * mix(0.45, 1.0, depth);
  col += max(hl, 0.0) * 0.30 * exp(-depth * 3.4) * uSway;

  /* ---------- 天空 ---------- */

  float skyT = clamp(-d / max(uHorizon, 1e-4), 0.0, 1.0);
  vec3 sky = mix(uSkyLow, uSkyMid, smoothstep(0.0, 0.42, skyT));
  sky = mix(sky, uSkyHigh, smoothstep(0.34, 1.0, skyT));

  float cloud = noise(vec2(nx * 1.5, skyT * 3.4) + vec2(uTime * 0.0016, 0.0));
  sky += (cloud - 0.5) * 0.035 * smoothstep(0.05, 0.8, skyT);

  /* ---------- 星光（只在夜里出现） ----------
     极慢的闪烁，周期约 60 秒；数量稀疏，避免变成噪点。 */
  if (uStars > 0.01) {
    vec2 sp = uv * vec2(aspect, 1.0) * 90.0;
    vec2 cell = floor(sp);
    float h = hash(cell);
    if (h > 0.9925) {
      vec2 center = cell + 0.5;
      float dist = length(sp - center);
      float tw = 0.55 + 0.45 * sin(uTime * 0.10 + h * 90.0);
      float star = smoothstep(0.42, 0.0, dist) * tw;
      /* 越靠上越多，接近海平线时被雾气吃掉 */
      star *= smoothstep(0.02, 0.45, skyT) * uStars;
      sky += vec3(star) * 0.85;
    }
  }

  /* ---------- 合成 ---------- */

  vec3 finalCol = mix(sky, col, sea);

  float band = exp(-abs(d) * 34.0);
  finalCol = mix(finalCol, uHorizonCol, band * 0.55);

  float vig = smoothstep(1.15, 0.25, length((uv - vec2(0.5, 0.46)) * vec2(1.0, 1.1)));
  finalCol *= mix(0.86, 1.0, vig);

  float lum = dot(finalCol, vec3(0.2126, 0.7152, 0.0722));
  finalCol = mix(vec3(lum), finalCol, 0.88);

  gl_FragColor = vec4(finalCol, 1.0);
}`;

  /* ---------------------------------------------------------------
     三、WebGL 初始化（任何一步失败都回退到 CSS 海面）
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

  const UNIFORMS = ["uRes", "uTime", "uHorizon", "uSway",
    "uSkyHigh", "uSkyMid", "uSkyLow", "uSeaFar", "uSeaMid", "uSeaNear",
    "uHorizonCol", "uStars"];

  let gl = null;
  let program = null;
  const loc = {};

  function initGL() {
    const opts = {
      alpha: false,
      antialias: false,
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

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const aPos = gl.getAttribLocation(program, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    UNIFORMS.forEach((name) => { loc[name] = gl.getUniformLocation(program, name); });
  }

  function resize() {
    if (!gl) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  /* 分段常量的色板：随时间平滑变化 */
  function currentPalette() {
    const now = new Date();
    const hour = now.getHours() + now.getMinutes() / 60;
    const pal = blendedPalette(phaseWeights(hour));
    return pal;
  }

  function draw(seconds) {
    const pal = currentPalette();
    gl.uniform2f(loc.uRes, canvas.width, canvas.height);
    gl.uniform1f(loc.uTime, seconds);
    gl.uniform1f(loc.uHorizon, readHorizon());
    gl.uniform1f(loc.uSway, pal.sway);
    gl.uniform3fv(loc.uSkyHigh, pal.skyHigh);
    gl.uniform3fv(loc.uSkyMid, pal.skyMid);
    gl.uniform3fv(loc.uSkyLow, pal.skyLow);
    gl.uniform3fv(loc.uSeaFar, pal.seaFar);
    gl.uniform3fv(loc.uSeaMid, pal.seaMid);
    gl.uniform3fv(loc.uSeaNear, pal.seaNear);
    gl.uniform3fv(loc.uHorizonCol, pal.horizon);
    gl.uniform1f(loc.uStars, Math.max(0, pal.night * 1.15 - 0.15));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    return pal;
  }

  /* 把当前色板的关键颜色同步给 DOM（CHEN、海面上的东西），
     这样文字与剪影随一天中的时间一起变，不会出现「夜里白字」 */
  function syncDomColors(pal) {
    const root = document.documentElement;
    const lum = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    const css = (c) => `rgb(${c.map((v) => Math.round(Math.max(0, Math.min(1, v)) * 255)).join(",")})`;
    const skyLum = lum(pal.skyMid);

    root.style.setProperty("--ocean-name", skyLum > 0.42 ? "rgba(18,26,34,.78)" : "rgba(232,240,246,.82)");
    root.style.setProperty("--ocean-object", skyLum > 0.42 ? "rgba(18,26,34,.62)" : "rgba(236,244,250,.72)");
    root.style.setProperty("--ocean-hint", skyLum > 0.42 ? "rgba(18,26,34,.42)" : "rgba(226,236,244,.42)");
    void css;
  }

  let rafId = 0;
  let start = 0;
  let lastPaletteSync = 0;

  function loop(now) {
    if (!start) start = now;
    const seconds = (now - start) * 0.001;
    const pal = draw(seconds);
    // 色板每分钟同步一次 DOM 就够了（跨时段才有变化）
    if (now - lastPaletteSync > 60000) {
      lastPaletteSync = now;
      syncDomColors(pal);
    }
    updateObjects(seconds);
    rafId = requestAnimationFrame(loop);
  }

  function bootGL() {
    try {
      initGL();
    } catch (error) {
      canvas.style.display = "none";
      console.error("[ocean] WebGL 初始化失败，已回退到静态海面：", error);
      showNote(`海面以静态方式呈现（<code>${String(error.message || error).slice(0, 90)}</code>）`);
      return false;
    }

    resize();
    window.addEventListener("resize", resize, { passive: true });

    const pal = draw(42.0);
    syncDomColors(pal);
    lastPaletteSync = performance.now();

    if (reduceMotion) return true;   // 只画静止的一帧

    rafId = requestAnimationFrame(loop);
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
     四、海面上的东西 —— 网站隐喻的入口
     每个东西对应一个真实分区；点它进入那个分区。
     不是菜单：任意时刻最多三个可见，40—70 秒一轮淡入淡出。
     --------------------------------------------------------------- */

  /* 海面上的东西用「CSS 形状」而不是文字符号：
     文字符号在不同字体下差异很大（有的是彩色 emoji，有的缺字），
     形状则各平台一致，也能做到真正的「很小」。

     每个形状用少量 div 拼出剪影，颜色统一走 --ocean-object，
     随一天中的时间在深色 / 浅色之间切换。 */
  const SHAPES = {
    /* 一艘小船：帆 + 船身 */
    boat: `<span class="sh sh-boat">
        <span class="sh-sail"></span>
        <span class="sh-hull"></span>
      </span>`,
    /* 一只鸟：两笔弧线 */
    bird: `<span class="sh sh-bird">
        <span class="sh-wing sh-wing-l"></span>
        <span class="sh-wing sh-wing-r"></span>
      </span>`,
    /* 一道很远的光：一个点 + 光晕（带极慢呼吸） */
    light: `<span class="sh sh-light"><span class="sh-glow"></span></span>`,
    /* 一个浮标 */
    buoy: `<span class="sh sh-buoy">
        <span class="sh-buoy-top"></span>
        <span class="sh-buoy-body"></span>
      </span>`,
    /* 一颗星：四角十字 */
    star: `<span class="sh sh-star">
        <span class="sh-star-v"></span>
        <span class="sh-star-h"></span>
      </span>`
  };

  const LABELS = {
    boat: "一艘船", bird: "一只鸟", light: "一道很远的光",
    buoy: "一个浮标", star: "一颗星"
  };

  /* 哪个分组配哪种东西，以及它出现在哪里（归一化坐标，uv.y 从下往上）。

     时间参数是算出来的，不是凭感觉定的：
       五个相位均分一圈（0 / 0.2 / 0.4 / 0.6 / 0.8），周期统一 75 秒，
       每轮停留 30 秒（占 40%）。
       这样相位差恒为 0.2、可见区间长 0.40 ——「任意时刻最多两个可见」
       是硬保证（实测最多 2 个，平均 1.63 个，每个至少出现 33% 的时间）。

     为什么周期必须统一：周期各不相同时，相位相对关系会缓慢漂移，
     漂够久必然出现「五个撞在一起」的时刻，「最多三个」就无法保证。
     统一周期换来的是稳定的潮汐感，对「安静的海」是加分。 */
  const CAST = [
    { group: "listen", kind: "boat", x: 0.24, y: 0.500, period: 75, dur: 30, phase: 0.0 },
    { group: "read", kind: "bird", x: 0.62, y: 0.565, period: 75, dur: 30, phase: 0.2 },
    { group: "watch", kind: "light", x: 0.80, y: 0.528, period: 75, dur: 30, phase: 0.4 },
    { group: "make", kind: "buoy", x: 0.14, y: 0.428, period: 75, dur: 30, phase: 0.6 },
    { group: "think", kind: "star", x: 0.47, y: 0.735, period: 75, dur: 30, phase: 0.8 }
  ];

  let castEls = [];
  let horizonN = 0.58;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));
  }

  async function buildCast() {
    if (!objectsEl) return;
    objectsEl.classList.add("is-loading");

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

      const href = {};
      nav.groups.forEach((g) => {
        if (g.pending || !Array.isArray(g.children) || !g.children.length) return;
        href[g.key] = g.children[0].href;
      });

      const usable = CAST.filter((c) => href[c.group]);
      if (!usable.length) {
        // 没有可用分区时不留空白：给出明确说明
        showNote("海面上暂时没有可以辨认的东西。");
        objectsEl.classList.remove("is-loading");
        return;
      }

      objectsEl.innerHTML = usable.map((c) => {
        const shape = SHAPES[c.kind] || "";
        const label = LABELS[c.kind] || c.group;
        return `<a class="floater" href="${esc(href[c.group])}"
                   data-group="${esc(c.group)}" data-kind="${esc(c.kind)}"
                   data-x="${c.x}" data-y="${c.y}"
                   data-period="${c.period}" data-dur="${c.dur}" data-phase="${c.phase}"
                   aria-label="${esc(label)} —— 去 ${esc(c.group)}"
                   title="${esc(c.group)}">${shape}</a>`;
      }).join("");

      castEls = Array.prototype.slice.call(objectsEl.querySelectorAll(".floater"));
      objectElsReady();
      objectsEl.classList.remove("is-loading");
    } catch (error) {
      objectsEl.classList.remove("is-loading");
      const reason = error && error.name === "AbortError"
        ? "请求超时（8 秒）" : String(error && error.message || error);
      console.error("[ocean] 海面上的东西加载失败：", error);
      showNote(`入口加载失败：<code>${esc(reason)}</code>`);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  function objectElsReady() {
    horizonN = readHorizon();
    // 立刻按当前时间摆好位置，避免第一帧挤在左上角
    castEls.forEach((el) => {
      el.style.left = `${parseFloat(el.dataset.x) * 100}%`;
      const top = (1 - parseFloat(el.dataset.y)) * 100;
      el.style.top = `${top}%`;
    });
    // ?all=1：全部显示，方便确认它们指向哪里
    if (showAll) castEls.forEach((el) => { el.style.opacity = "0.9"; });
  }

  /* 每个东西有自己的周期：缓慢淡入 -> 停留 -> 淡出 -> 消失一段时间。
     任意时刻可见的通常不超过三个。 */
  function updateObjects(seconds) {
    if (!castEls.length || showAll) return;
    const vh = window.innerHeight || 1;
    castEls.forEach((el) => {
      const period = parseFloat(el.dataset.period);
      const dur = parseFloat(el.dataset.dur);
      const phase = parseFloat(el.dataset.phase);
      const t = (seconds / period + phase) % 1;
      const up = Math.min(dur / period, 0.95);

      let a = 0;
      if (t < up) {
        const p = t / up;
        // 前后各 22% 做淡入淡出，中间停留
        a = Math.min(smooth01(p / 0.22), smooth01((1 - p) / 0.22));
      }
      el.style.opacity = a.toFixed(3);
      el.style.pointerEvents = a > 0.35 ? "auto" : "none";
      el.setAttribute("aria-hidden", a > 0.35 ? "false" : "true");

      // 极轻微的上下浮动：像水面上的东西随波起伏（幅度 3px 以内）
      const baseTop = (1 - parseFloat(el.dataset.y)) * 100;
      const bob = Math.sin(seconds * 0.22 + phase * 6.28) * (3 / vh) * 100;
      el.style.transform = `translate(-50%, -50%) translateY(${bob.toFixed(3)}%)`;
      void horizonN;
    });
  }

  function smooth01(x) {
    const t = Math.max(0, Math.min(1, x));
    return t * t * (3 - 2 * t);
  }

  /* ---------------------------------------------------------------
     五、启动
     --------------------------------------------------------------- */

  if (canvas) bootGL();
  else showNote("找不到海面画布。");

  buildCast();

  /* 暴露少量内部函数，便于在控制台核对当前时段与色板：
       __ocean.palette()   -> 此刻实际使用的调色板
       __ocean.weights(20) -> 20 点时的三段权重
       __ocean.cast()      -> 海面上东西的位置与可见度
     只读用途，不影响渲染。 */
  window.__ocean = {
    weights: phaseWeights,
    palette: () => blendedPalette(phaseWeights(new Date().getHours() + new Date().getMinutes() / 60)),
    palettes: PALETTES,
    cast: () => castEls.map((el) => ({
      group: el.dataset.group,
      kind: el.dataset.kind,
      href: el.getAttribute("href"),
      opacity: Number(el.style.opacity || 0)
    }))
  };
})();
