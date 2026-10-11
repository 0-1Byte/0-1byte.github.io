/* 在 Node 里跑真实的 /quotes.js，验证打字机行为：
     A. 打字：逐字增加，不是一次性显示
     B. 完成后光标变暗（is-done）
     C. 出处显示 / 隐藏
     D. empty：句子库为空 -> 兜底句 + console.warn
     E. error：内联数据无效 -> 显示兜底句 + console.warn（不打扰访客）
     F. prefers-reduced-motion -> 直接显示整句
     G. 超长句子截断
     H. 尽量避开上一句（localStorage 记忆）
   脚本取自 static/quotes.js。 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const STATIC = path.join(ROOT, "static");
const src = fs.readFileSync(path.join(STATIC, "quotes.js"), "utf8");
const layoutSrc = fs.readFileSync(path.join(ROOT, "layouts", "index.html"), "utf8");

let problems = 0;
const fail = (m) => { problems++; console.log("      ✗ " + m); };
const ok = (m) => console.log("      " + m);

function makeEl(id, cls) {
  const el = {
    id, _classes: new Set(cls ? cls.split(" ") : []),
    textContent: "", hidden: false, _handlers: {}, _attrs: {},
    clientWidth: 680, complete: false, naturalWidth: 0, src: "",
    classList: {
      add(c) { el._classes.add(c); },
      remove(c) { el._classes.delete(c); },
      contains(c) { return el._classes.has(c); }
    },
    // 属性接口：quotes.js 会用 setAttribute/removeAttribute 标记 data-has-dash
    // （出处自带破折号时抑制 CSS 的前缀）。桩里少了它们会让打字循环中途抛错，
    // 表现成「没有逐字输出」——那是测试桩的问题，不是产品代码的问题。
    setAttribute(k, v) { el._attrs[k] = String(v); },
    getAttribute(k) { return k in el._attrs ? el._attrs[k] : null; },
    removeAttribute(k) { delete el._attrs[k]; },
    hasAttribute(k) { return k in el._attrs; },
    querySelector(sel) {
      if (sel === "[data-quote-text]") return elsRef.text;
      if (sel === ".home-focus-caret") return elsRef.caret;
      return null;
    },
    addEventListener(t, fn) { (el._handlers[t] ||= []).push(fn); },
    closest() { return null; }
  };
  return el;
}

let elsRef = {};

function setup(opts, serializedQuotes) {
  const host = makeEl("home-focus", "home-focus is-loading");
  host.clientWidth = opts.width || 680;
  const text = makeEl("home-focus-text");
  const caret = makeEl("home-focus-caret");
  const source = makeEl("home-focus-source");
  const quotes = makeEl("home-quotes");
  quotes.textContent = serializedQuotes;
  const backgrounds = makeEl("home-backgrounds");
  backgrounds.getAttribute = (name) => name === "data-home-backgrounds"
    ? JSON.stringify(opts.backgrounds || [])
    : name === "data-home-backgrounds-optimized" ? String(Boolean(opts.optimized)) : null;
  const backgroundImage = makeEl("home-background-image");
  text.textContent = opts.serverText || "";
  elsRef = { host, text, caret, source };

  const doc = {
    getElementById: (id) => id === "home-focus" ? host : id === "home-quotes" ? quotes : null,
    querySelector: (sel) => {
      if (sel === "[data-quote-source]") return source;
      if (sel === "[data-home-backgrounds]") return backgrounds;
      if (sel === "[data-home-background-image]") return opts.backgrounds ? backgroundImage : null;
      return null;
    },
    createElement: (tag) => tag === "canvas" ? ({
      getContext: () => ({
        font: "",
        measureText(text) {
          return { width: Array.from(text).reduce((width, char) =>
            width + (/[\u2e80-\u9fff\uf900-\ufaff]/.test(char) ? 34 : /\s/.test(char) ? 8 : 17), 0) };
        }
      })
    }) : null,
    addEventListener() {},
    documentElement: { dataset: {} },
    hidden: false
  };
  const win = {
    WEREAD_SYNC_API_BASE: opts.apiBase || "",
    location: {
      hostname: opts.hostname || "example.com",
      search: opts.search || ""
    },
    matchMedia: (q) => ({
      matches: q.includes("reduced-motion")
        ? opts.reduceMotion === true
        : q.includes("max-width") && opts.mobile === true
    }),
    getComputedStyle: () => ({
      fontStyle: "normal",
      fontVariant: "normal",
      fontWeight: "400",
      fontSize: `${opts.fontSize || 34}px`,
      fontFamily: "serif",
      letterSpacing: "0px"
    }),
    _handlers: {},
    addEventListener(type, fn) { (this._handlers[type] ||= []).push(fn); }
  };
  return { doc, win, els: elsRef, backgroundImage };
}

async function run(opts, serializedQuotes = "[]") {
  const env = setup(opts, serializedQuotes);
  const store = opts.store || {};
  const warns = [];
  const con = { ...console, warn: (...a) => warns.push(a.map(String).join(" ")), error: () => {} };
  const clock = opts.fakeTimers ? {
    now: 0,
    nextId: 1,
    timers: new Map(),
    scheduledDelays: [],
    setTimeout(fn, delay) {
      const id = this.nextId++;
      const wait = Number(delay) || 0;
      this.scheduledDelays.push(wait);
      this.timers.set(id, { fn, due: this.now + wait });
      return id;
    },
    clearTimeout(id) {
      this.timers.delete(id);
    },
    runNext() {
      let nextId = 0;
      let nextTimer = null;
      for (const [id, timer] of this.timers) {
        if (!nextTimer || timer.due < nextTimer.due) {
          nextId = id;
          nextTimer = timer;
        }
      }
      if (!nextTimer) return false;
      this.timers.delete(nextId);
      this.now = nextTimer.due;
      nextTimer.fn();
      return true;
    }
  } : null;

  const savedDoc = global.document, savedWin = global.window, savedLs = global.localStorage;
  const savedFetch = global.fetch;
  const savedRandom = Math.random;
  global.document = env.doc;
  global.window = env.win;
  global.fetch = opts.fetch || savedFetch;
  if (opts.randomValues) {
    let randomIndex = 0;
    Math.random = () => opts.randomValues[randomIndex++] ?? opts.randomValues[opts.randomValues.length - 1] ?? 0.5;
  }
  global.localStorage = {
    setItem(k, v) { store[k] = v; },
    getItem(k) { return store[k] === undefined ? null : store[k]; }
  };
  try {
    new Function("document", "window", "navigator", "console", "localStorage",
      "setTimeout", "setInterval", "clearTimeout", src)(
      env.doc, env.win, { hardwareConcurrency: 8 }, con, global.localStorage,
      clock ? clock.setTimeout.bind(clock) : setTimeout,
      () => 1,
      clock ? clock.clearTimeout.bind(clock) : clearTimeout);
    if (opts.onInit) opts.onInit({ ...env, clock });
    if (!clock) await new Promise((r) => setTimeout(r, opts.wait || 300));
  } finally {
    global.document = savedDoc; global.window = savedWin; global.localStorage = savedLs;
    global.fetch = savedFetch;
    Math.random = savedRandom;
  }
  return { ...env, warns, store, clock };
}

const quotesFetch = (list) => JSON.stringify(list);

function checkBuiltHomepageQuotes() {
  const indexPath = process.argv[2]
    ? path.resolve(process.argv[2])
    : path.join(ROOT, "public", "index.html");
  console.log(`构建产物隐私检查：${indexPath} 内联手动句子`);
  let html;
  try {
    html = fs.readFileSync(indexPath, "utf8");
  } catch (error) {
    fail(`无法读取构建产物 ${indexPath}；请先运行 Hugo 生产构建`);
    return;
  }

  const match = html.match(/<script\b(?=[^>]*\bid\s*=\s*(?:"home-quotes"|'home-quotes'|home-quotes)(?=\s|>))[^>]*>([\s\S]*?)<\/script\s*>/i);
  if (!match) {
    fail("构建产物中缺少 #home-quotes JSON script 标签");
    return;
  }

  let data;
  try {
    data = JSON.parse(match[1]);
  } catch (error) {
    fail(`#home-quotes 内容不能由一次 JSON.parse() 解析：${error.message}`);
    return;
  }
  if (!data || typeof data !== "object" || Array.isArray(data)
    || !Array.isArray(data.manual) || Object.keys(data).some((key) => key !== "manual")) {
    fail("#home-quotes 只能包含 manual 数组，不得内嵌 WeRead 数据");
    return;
  }
  if (!data.manual.every((quote) => quote && typeof quote.text === "string"
    && quote.text.trim() && typeof quote.source === "string"
    && quote.source_type === "manual")) {
    fail("手动来源的句子必须包含 text/source，并使用 source_type=manual");
    return;
  }
  if (/"(?:book_id|chapter_uid|bookmark_id|also_sources)"\s*:/.test(match[1])) {
    fail("#home-quotes 包含被禁止公开的内部元数据");
    return;
  }
  if (/site\.Data\.weread_quotes|data\/weread_quotes\.json/.test(layoutSrc)) {
    fail("首页模板仍然读取本地完整 WeRead 数据集");
    return;
  }
  if (fs.existsSync(path.join(path.dirname(indexPath), "data", "weread_quotes.json"))) {
    fail("构建产物公开目录中存在完整 WeRead JSON 文件");
    return;
  }
  if (!html.includes("admin/weread-sync/config.js")) {
    fail("首页缺少 Worker 地址配置脚本");
    return;
  }
  ok(`#home-quotes 只包含 manual=${data.manual.length} 条；没有内嵌 WeRead 数据或内部字段`);
}

/* 出处自带破折号时，应加 data-has-dash 让 CSS 的 ::before 不要重复加前缀。
   pages.css 的规则：
     .hero--quote .home-focus-source:not([hidden]):not([data-has-dash])::before
   数据格式不变，靠这个属性避免出现「— — 某某」。 */
async function checkDashGuard() {
  console.log();
  console.log("I. 出处破折号抑制（data-has-dash）");
  const CASES = [
    ["普通出处", "Steve Jobs", false],
    ["全角破折号开头", "— Steve Jobs", true],
    ["中文破折号开头", "—— 某人", true],
    ["连字符开头", "- Someone", true],
    ["前导空格后破折号", "   — X", true],
    ["出处中间有破折号", "书 · 作者 — 注", false],
  ];
  let bad = 0;
  for (const [label, source, shouldHave] of CASES) {
    const r = await run({ wait: 300, reduceMotion: true },
      quotesFetch([{ text: "句子", source }]));
    const has = r.els.source.hasAttribute("data-has-dash");
    const ok = has === shouldHave;
    if (!ok) { bad++; problems++; }
    console.log(`  ${ok ? "OK " : "FAIL"} ${label.padEnd(12)} source=${JSON.stringify(source).padEnd(20)} ` +
      `data-has-dash=${has}（期望 ${shouldHave}）`);
  }
  // 无出处时不该残留属性
  const none = await run({ wait: 300, reduceMotion: true }, quotesFetch([{ text: "句子", source: "" }]));
  const leftover = none.els.source.hasAttribute("data-has-dash");
  if (leftover) { bad++; problems++; }
  console.log(`  ${leftover ? "FAIL" : "OK "} 无出处时不残留属性  data-has-dash=${leftover}`);
  return bad;
}

(async () => {
  checkBuiltHomepageQuotes();

  console.log("0. 首屏句子不等待背景图片");
  let initialText = null;
  let initialDelay = null;
  const waiting = await run({
    fakeTimers: true,
    backgrounds: [{ src: "/home/backgrounds/test.jpg" }],
    randomValues: [0.5],
    onInit: ({ els, clock }) => {
      initialText = els.text.textContent;
      initialDelay = clock.scheduledDelays[0];
    }
  }, quotesFetch([{ text: "随机句子", source: "" }]));
  if (waiting.els.host.classList.contains("is-loading")) fail("有效内联数据时句子区应立即解除 loading");
  else ok("有效内联数据时句子区立即解除 loading");
  if (initialText !== "") fail(`220ms 起始延迟前文本必须为空，实际：[${initialText}]`);
  else ok("220ms 起始延迟前文本为空");
  if (initialDelay !== 220) fail(`首次打字延迟应为 220ms，实际 ${initialDelay}ms`);
  else ok("首次打字延迟为 220ms");
  if (waiting.backgroundImage.src !== "/home/backgrounds/test.jpg") {
    fail("背景请求没有在后台开始加载");
  } else ok("背景已独立启动，未阻塞句子初始化");
  waiting.clock.runNext();
  if (Array.from(waiting.els.text.textContent).length !== 1) {
    fail(`首个打字定时器应显示一个字符，实际：[${waiting.els.text.textContent}]`);
  } else ok("首个打字定时器后恰好显示一个字符");
  const beforeNextStep = waiting.els.text.textContent;
  waiting.clock.runNext();
  if (Array.from(waiting.els.text.textContent).length !== Array.from(beforeNextStep).length + 1) {
    fail("后续定时器应只增加一个字符");
  } else ok("后续定时器只增加一个字符");

  console.log("0.1 响应式 WebP 变体、最近背景避让与原图回退");
  const backgroundStore = {
    "home-background-recent": JSON.stringify(["recent-a.jpg", "recent-b.jpg"])
  };
  const backgroundResult = await run({
    wait: 50,
    mobile: true,
    optimized: true,
    store: backgroundStore,
    backgrounds: [
      { src: "/home/backgrounds/recent-a.jpg" },
      { src: "/home/backgrounds/recent-b.jpg" },
      { src: "/home/backgrounds/available.jpg" }
    ]
  }, quotesFetch([{ text: "图片不阻塞句子", source: "" }]));
  if (backgroundResult.backgroundImage.src !== "/home/backgrounds-optimized/available--jpg--mobile.webp") {
    fail(`移动端应选择排除近期背景后的 WebP 变体，实际 ${backgroundResult.backgroundImage.src}`);
  } else ok("手机选中单张 mobile WebP，最近两张背景仍被排除");
  backgroundResult.backgroundImage._handlers.error[0]();
  if (backgroundResult.backgroundImage.src !== "/home/backgrounds/available.jpg") {
    fail("WebP 加载失败时应回退到原图");
  } else ok("WebP 失败时回退到原图，句子保持可见");
  const desktopBackground = await run({
    wait: 50,
    optimized: true,
    backgrounds: [{ src: "/home/backgrounds/available.jpg" }]
  }, quotesFetch([{ text: "桌面背景", source: "" }]));
  if (desktopBackground.backgroundImage.src !== "/home/backgrounds-optimized/available--jpg--desktop.webp") {
    fail(`桌面端应选择 desktop WebP 变体，实际 ${desktopBackground.backgroundImage.src}`);
  } else ok("桌面端选中单张 desktop WebP 变体");

  console.log("0.2 随机选句与上一句避让");
  const quoteStore = { "home-quote-seen": "前一句" };
  const randomPick = await run({
    wait: 250,
    reduceMotion: true,
    store: quoteStore,
    randomValues: [0, 0.99]
  }, quotesFetch([{ text: "前一句" }, { text: "新句子" }]));
  if (randomPick.els.text.textContent !== "新句子") {
    fail(`上一句避让未生效，选中：[${randomPick.els.text.textContent}]`);
  } else ok("刷新抽取随机候选，并避开 localStorage 中的上一句");

  console.log();
  console.log("0.3 Worker 单条读取、双来源独立随机与降级");
  const manual = [{ text: "手动来源测试", source: "" }];
  const remoteQuote = {
    text: "WeRead来源测试",
    source_type: "weread",
    source: "合成测试书",
    author: "合成作者",
    chapter: "合成章节",
    book_id: "must-not-reach-browser"
  };
  let remoteRequest = null;
  const fetchWeread = async (url, options) => {
    remoteRequest = { url, options };
    return new Response(JSON.stringify(remoteQuote), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  };
  const manualOnly = await run({ wait: 1, reduceMotion: true, randomValues: [0] },
    JSON.stringify({ manual }));
  const wereadOnly = await run({
    wait: 1,
    reduceMotion: true,
    apiBase: "https://worker.example",
    fetch: fetchWeread
  }, JSON.stringify({ manual: [] }));
  if (manualOnly.els.text.textContent !== "手动来源测试") fail("仅手动来源时应显示手动句子");
  else ok("仅手动来源可正常显示");
  if (wereadOnly.els.text.textContent !== "WeRead来源测试") fail("仅 WeRead 来源时应显示 WeRead 句子");
  else ok("仅 WeRead 来源可正常显示");
  if (wereadOnly.els.source.textContent !== "《合成测试书》 · 合成作者 · 合成章节") {
    fail("WeRead 出处应按书名、作者、章节显示");
  } else ok("WeRead 出处使用书名、作者和章节字段");
  if (!remoteRequest || remoteRequest.url !== "https://worker.example/public/quote"
    || remoteRequest.options.credentials !== "omit") {
    fail("首页应以无凭据 GET 请求 Worker 的单条随机接口");
  } else ok("首页只请求 Worker 单条接口且不发送浏览器凭据");

  console.log("0.3.1 本地开发模式必须显式启用且仅适用于回环主机");
  let localRequest = null;
  const localDevFetch = async (url, options) => {
    localRequest = { url, options };
    return fetchWeread(url, options);
  };
  await run({
    wait: 1,
    reduceMotion: true,
    hostname: "localhost",
    search: "?wereadDev=1",
    apiBase: "https://worker.example",
    randomValues: [0.999],
    fetch: localDevFetch
  }, JSON.stringify({ manual }));
  if (!localRequest || localRequest.url !== "http://127.0.0.1:8765/public/quote") {
    fail("localhost + wereadDev=1 时应使用固定本地接口");
  } else if (localRequest.options.cache !== "no-store") {
    fail("本地接口请求应禁用浏览器缓存");
  } else ok("localhost + wereadDev=1 启用本地接口并禁用缓存");

  let repeatedLocalRequests = 0;
  const repeatedLocalFetch = async (url, options) => {
    repeatedLocalRequests += 1;
    return fetchWeread(url, options);
  };
  const repeatedOne = await run({
    wait: 1,
    reduceMotion: true,
    hostname: "127.0.0.1",
    search: "?wereadDev=1",
    randomValues: [0.999],
    fetch: repeatedLocalFetch
  }, JSON.stringify({ manual }));
  const repeatedTwo = await run({
    wait: 1,
    reduceMotion: true,
    hostname: "127.0.0.1",
    search: "?wereadDev=1",
    randomValues: [0.999],
    fetch: repeatedLocalFetch
  }, JSON.stringify({ manual }));
  if (repeatedLocalRequests !== 2
    || repeatedOne.els.text.textContent !== "WeRead来源测试"
    || repeatedTwo.els.text.textContent !== "WeRead来源测试") {
    fail("每次新的首页初始化都应重新请求并展示本地 WeRead 单条结果");
  } else ok("重复初始化各自重新请求并显示 WeRead 结果");

  let nonLocalRequest = null;
  await run({
    wait: 1,
    reduceMotion: true,
    hostname: "0-1byte.github.io",
    search: "?wereadDev=1",
    apiBase: "https://worker.example",
    randomValues: [0.999],
    fetch: async (url, options) => {
      nonLocalRequest = { url, options };
      return fetchWeread(url, options);
    }
  }, JSON.stringify({ manual }));
  if (!nonLocalRequest || nonLocalRequest.url !== "https://worker.example/public/quote") {
    fail("非本机主机即使带开发参数也必须只请求 Worker");
  } else ok("非本机主机忽略开发参数并继续请求 Worker");

  let noFlagRequest = null;
  await run({
    wait: 1,
    reduceMotion: true,
    hostname: "127.0.0.1",
    apiBase: "https://worker.example",
    randomValues: [0.999],
    fetch: async (url, options) => {
      noFlagRequest = { url, options };
      return fetchWeread(url, options);
    }
  }, JSON.stringify({ manual }));
  if (!noFlagRequest || noFlagRequest.url !== "https://worker.example/public/quote") {
    fail("本机未显式启用时必须继续使用配置的 Worker");
  } else ok("本机未提供 wereadDev=1 时仍请求 Worker");
  if (JSON.stringify(wereadOnly.els.source.textContent).includes("must-not-reach-browser")) {
    fail("浏览器不得显示 Worker 白名单之外的字段");
  } else ok("浏览器忽略 Worker 响应中的内部字段");

  const legacyWeread = await run({ wait: 1, reduceMotion: true },
    JSON.stringify({ manual: [], weread: [{ text: "旧记录", source: "weread" }] }));
  if (!legacyWeread.els.text.textContent.includes("building small things")) {
    fail("旧内嵌 WeRead 数据不得被作为有效来源");
  } else ok("忽略旧内嵌 WeRead 数据，显示兜底句");

  let manualSelections = 0;
  let wereadSelections = 0;
  for (let i = 0; i < 200; i += 1) {
    const selected = await run({
      wait: 1,
      reduceMotion: true,
      apiBase: "https://worker.example",
      randomValues: [i % 2 === 0 ? 0 : 0.999],
      fetch: fetchWeread
    }, JSON.stringify({
      manual: [{ text: "手动池较小", source: "" }]
    }));
    if (selected.els.text.textContent === "手动池较小") manualSelections += 1;
    if (selected.els.source.textContent.indexOf("《合成测试书》") === 0) wereadSelections += 1;
  }
  if (manualSelections !== 100 || wereadSelections !== 100) {
    fail(`来源概率应各约 50%，本次 manual=${manualSelections} weread=${wereadSelections}`);
  } else ok(`200 次可控抽取按来源各 50%（manual=${manualSelections}, weread=${wereadSelections}）`);

  const missingWeread = await run({ wait: 1, reduceMotion: true, randomValues: [0] },
    JSON.stringify({ manual: [{ text: "手动回退", source: "" }] }));
  if (missingWeread.els.text.textContent !== "手动回退") fail("WeRead 来源缺失时应回退到手动来源");
  else ok("WeRead 数据缺失时回退到手动来源");

  const serviceUnavailable = await run({
    wait: 1,
    reduceMotion: true,
    apiBase: "https://worker.example",
    randomValues: [0.999],
    fetch: async () => new Response("{}", { status: 503 })
  }, JSON.stringify({ manual: [{ text: "服务失败回退", source: "" }] }));
  if (serviceUnavailable.els.text.textContent !== "服务失败回退") {
    fail("Worker 不可用时应回退到手动来源");
  } else ok("Worker 失败时平稳回退到手动句子");

  const timedOutRequest = await run({
    fakeTimers: true,
    wait: 1,
    reduceMotion: true,
    apiBase: "https://worker.example",
    randomValues: [0.999],
    fetch: () => new Promise(() => {}),
    onInit: ({ clock }) => clock.runNext()
  }, JSON.stringify({ manual: [{ text: "超时后回退", source: "" }] }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (timedOutRequest.els.text.textContent !== "超时后回退") {
    fail("Worker 超时时应回退到手动来源");
  } else ok("Worker 超时后平稳回退到手动句子");

  const bothEmpty = await run({ wait: 1, reduceMotion: true }, JSON.stringify({ manual: [] }));
  if (bothEmpty.els.text.textContent.replace(/\s+/g, " ").trim()
    !== "building small things, thinking about large things.") {
    fail("两个来源都为空时应显示兜底句");
  } else ok("两个来源均为空时显示兜底句");

  console.log("A. 打字过程（逐帧观察文本长度）");
  const long = {
    text: "这是一句用来观察打字过程的话。",
    source_type: "manual",
    source: "合成手动出处"
  };
  let typingInitialText = null;
  let typingInitialDelay = null;
  const typing = await run({
    fakeTimers: true,
    width: 3000,
    backgrounds: [{ src: "/home/backgrounds/pending.jpg" }],
    onInit: ({ els, clock }) => {
      typingInitialText = els.text.textContent;
      typingInitialDelay = clock.scheduledDelays[0];
    }
  }, quotesFetch([long]));
  if (typingInitialText !== "") fail(`打字开始前文本必须为空，实际：[${typingInitialText}]`);
  else ok("打字开始前文本为空");
  if (typingInitialDelay !== 220) fail(`首次打字延迟应为 220ms，实际 ${typingInitialDelay}ms`);
  else ok("首次打字定时器延迟为 220ms");
  if (typing.backgroundImage.src !== "/home/backgrounds/pending.jpg") {
    fail("背景尚未加载时未启动句子打字");
  } else ok("背景请求仍在等待时，句子已进入打字流程");

  typing.clock.runNext();
  const first = typing.els.text.textContent;
  if (Array.from(first).length !== 1) fail(`首个定时器应只显示一个字符，实际：[${first}]`);
  else ok(`首个定时器后只显示首字：[${first}]`);
  typing.clock.runNext();
  const second = typing.els.text.textContent;
  if (Array.from(second).length !== Array.from(first).length + 1) {
    fail(`后续定时器应只增加一个字符，实际：[${first}] -> [${second}]`);
  } else ok("后续定时器逐字符增加");
  let previous = second;
  let oneCharacterPerStep = true;
  while (typing.clock.timers.size) {
    typing.clock.runNext();
    const current = typing.els.text.textContent;
    if (Array.from(current).length !== Array.from(previous).length + 1) {
      oneCharacterPerStep = false;
      break;
    }
    previous = current;
  }
  if (!oneCharacterPerStep) fail("长句余下各步必须严格逐字符输出");
  const end = typing.els.text.textContent;
  if (end !== long.text) fail(`最终文本与句子不一致：[${end}]`);
  else ok("长句逐字输出并完整结束");
  if (!typing.els.caret._classes.has("is-done")) fail("打完后光标未标记 is-done");
  else ok("打完后光标变暗（is-done）");
  if (typing.els.source.textContent
    !== "合成手动出处") {
    fail("手动句子出处显示错误");
  }
  else ok("手动句子出处维持原有显示行为");

  console.log();
  console.log("A.1 短句逐字输出");
  let shortInitialText = null;
  const shortTyping = await run({
    fakeTimers: true,
    onInit: ({ els }) => { shortInitialText = els.text.textContent; }
  }, quotesFetch([{ text: "猫", source: "" }]));
  if (shortInitialText !== "") fail("短句打字开始前文本必须为空");
  shortTyping.clock.runNext();
  if (shortTyping.els.text.textContent !== "猫") fail("短句首个定时器后应显示完整的一字句");
  else ok("一字短句等待起始延迟后显示，未提前闪现");
  if (!shortTyping.els.caret._classes.has("is-done")) fail("短句完成后光标应为完成态");

  console.log();
  console.log("B. 没有出处时整行隐藏");
  const noSrc = await run({ wait: 1200 }, quotesFetch([{ text: "只有句子。", source: "" }]));
  if (!noSrc.els.source.hidden) fail("无出处时 source 未隐藏");
  else ok("source hidden = true");

  console.log();
  console.log("C. empty：句子库为空");
  const empty = await run({ wait: 400 }, quotesFetch([]));
  if (empty.els.text.textContent.replace(/\s+/g, " ").trim() !== "building small things, thinking about large things.") {
    fail("空句子库时应显示完整兜底句");
  } else ok("保留兜底句，页面不空白");

  console.log();
  console.log("D. error：内联数据无效");
  const err = await run({ wait: 400 }, "{");
  console.log(`      文本 = [${err.els.text.textContent}]`);
  if (err.els.text.textContent.replace(/\s+/g, " ").trim() !== "building small things, thinking about large things.") {
    fail("请求失败时应显示完整兜底句");
  } else ok("请求失败时显示兜底句");
  if (!err.warns.some((w) => w.includes("手动句子数据无效"))) fail("无效内联数据应记录安全诊断");
  else ok(`console.warn：${err.warns[0].slice(0, 60)}`);

  console.log();
  console.log("E. 格式不对（缺 quotes 数组）");
  const badShape = await run({ wait: 400 }, JSON.stringify({ groups: [] }));
  if (!badShape.warns.some((w) => w.includes("手动句子数据无效"))) fail("缺手动句子数组时应走错误分支");
  else ok("走 error 分支并保留原句");

  console.log();
  console.log("F. prefers-reduced-motion：直接显示整句");
  const rm = await run({ wait: 250, reduceMotion: true },
    JSON.stringify([{ ...long, source_type: "manual", source: "" }]));
  console.log(`      250ms 时文本长度 = ${Array.from(rm.els.text.textContent).length}`);
  if (rm.els.text.textContent !== long.text) fail("减少动效时应一次显示整句");
  else ok("一次显示整句，不打字");
  if (!rm.els.caret._classes.has("is-done")) fail("减少动效时光标应直接是完成态");
  else ok("光标直接为完成态");

  console.log();
  console.log("G. 自适应排版：中文语义断点、英文单词、显式换行");
  const semantic = "我们吞咽了太多意义，其实生命只需要呼吸。";
  const semanticResult = await run({ wait: 250, reduceMotion: true, width: 400 },
    quotesFetch([{ text: semantic }]));
  if (!semanticResult.els.text.textContent.includes("，\n")) {
    fail(`中文优先在逗号后断行，实际：[${semanticResult.els.text.textContent}]`);
  } else ok(`中文逗号语义断行：[${semanticResult.els.text.textContent}]`);

  const shortResult = await run({ wait: 250, reduceMotion: true, width: 680 },
    quotesFetch([{ text: "适时剪枝" }]));
  if (shortResult.els.text.textContent.includes("\n")) fail("短中文句不应被强制拆行");
  else ok("短中文句保持单行");

  const english = "building small things, thinking about large things.";
  const englishResult = await run({ wait: 250, reduceMotion: true, width: 280 },
    quotesFetch([{ text: english }]));
  if (!englishResult.els.text.textContent.includes("\n")) fail("窄宽度下英文长句应自然分行");
  const rejoinedEnglish = englishResult.els.text.textContent.replace(/\n/g, " ").replace(/\s+/g, " ").trim();
  if (rejoinedEnglish !== english) fail("英文断行不应拆词或丢失标点/空格");
  else ok(`英文按完整单词换行：[${englishResult.els.text.textContent}]`);

  const explicit = await run({ wait: 250, reduceMotion: true, width: 680 },
    quotesFetch([{ text: "Some people want diamond rings | Some just want everything" }]));
  if (!explicit.els.text.textContent.includes("\n")) fail("显式断点应保留为换行");
  else ok("显式断点保留");

  const longChinese = "他不再等一个更好的处境，才允许自己认真的生活。";
  const longChineseResult = await run({ wait: 250, reduceMotion: true, width: 400 },
    quotesFetch([{ text: longChinese }]));
  const longChineseLines = longChineseResult.els.text.textContent.split("\n");
  if (longChineseLines.length < 2 || longChineseLines.some((line) => /^[，。！？；：、,.!?;:]/u.test(line))) {
    fail("长中文句应自然分行且不能以标点开头");
  } else if (/^[\u2e80-\u9fff\uf900-\ufaff]{1,3}[，。！？；：、,.!?;:]?$/u.test(longChineseLines[longChineseLines.length - 1])) {
    fail("长中文句不应留下 1～3 字的孤儿行");
  } else ok(`长中文句的断行自然：[${longChineseLines.join(" / ")}]`);

  const mixed = "To See the world，并不是为了拥有答案。";
  const mixedResult = await run({ wait: 250, reduceMotion: true, width: 300 },
    quotesFetch([{ text: mixed }]));
  if (!mixedResult.els.text.textContent.split("\n").some((line) => /\bworld\b/.test(line))) {
    fail("中英混排时应保留完整英文单词");
  } else ok("中英混排中的英文单词未拆分");

  const punctuation = "认识你自己、凡事勿过度、妄立誓则祸近。";
  const punctuationResult = await run({ wait: 250, reduceMotion: true, width: 280 },
    quotesFetch([{ text: punctuation }]));
  if (punctuationResult.els.text.textContent.replace(/\n/g, "") !== punctuation) {
    fail("多个中文标点句的自动排版应保留全部字符");
  } else if (punctuationResult.els.text.textContent.split("\n").some((line) => /^[，。！？；：、]/u.test(line))) {
    fail("自动排版不应让中文标点出现在行首");
  } else ok(`多标点中文句保留顺序且断行正常：[${punctuationResult.els.text.textContent}]`);

  console.log();
  console.log("H. 显示完成后窗口变宽时重新排版");
  const resizeResult = await run({ wait: 250, reduceMotion: true, width: 280 },
    quotesFetch([{ text: semantic }]));
  const narrowLines = resizeResult.els.text.textContent.split("\n").length;
  resizeResult.els.host.clientWidth = 680;
  for (const handler of resizeResult.win._handlers.resize || []) handler();
  await new Promise((r) => setTimeout(r, 160));
  const wideLines = resizeResult.els.text.textContent.split("\n").length;
  if (wideLines >= narrowLines) fail("窗口变宽后应按新宽度重新计算断行");
  else ok(`窗口变宽后由 ${narrowLines} 行调整为 ${wideLines} 行`);

  console.log();
  console.log("I. 超长句子截断到 140 字符");
  const huge = { text: "字".repeat(300), source: "" };
  const cut = await run({ wait: 300, reduceMotion: true }, quotesFetch([huge]));
  const n = Array.from(cut.els.text.textContent).filter((char) => char !== "\n").length;
  console.log(`      显示长度 = ${n}`);
  if (n !== 140) fail(`应截断到 140，实际 ${n}`);
  else ok("截断到 140");

  console.log();
  console.log("J. 尽量避开上一句");
  const store = {};
  const two = [{ text: "AAA", source: "" }, { text: "BBB", source: "" }];
  const picks = [];
  for (let i = 0; i < 12; i++) {
    const r = await run({ wait: 250, reduceMotion: true, store }, quotesFetch(two));
    picks.push(r.els.text.textContent);
  }
  let repeats = 0;
  for (let i = 1; i < picks.length; i++) if (picks[i] === picks[i - 1]) repeats++;
  console.log(`      12 次抽取：${picks.join(" ")}`);
  console.log(`      相邻重复 ${repeats} 次（应接近 0）`);
  if (repeats > 1) fail(`相邻重复 ${repeats} 次偏多，避让逻辑可能失效`);
  else ok("相邻不重复（避让生效）");

  await checkDashGuard();

  console.log();
  console.log(`合计问题: ${problems}`);
  process.exit(problems ? 1 : 0);
})();
