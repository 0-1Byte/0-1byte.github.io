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
  global.document = env.doc;
  global.window = env.win;
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
  }
  return { ...env, warns, store, clock };
}

const quotesFetch = (list) => JSON.stringify(list);

function checkBuiltHomepageQuotes() {
  console.log("构建产物集成检查：public/index.html 内联句子");
  const indexPath = path.join(ROOT, "public", "index.html");
  let html;
  try {
    html = fs.readFileSync(indexPath, "utf8");
  } catch (error) {
    fail(`无法读取构建产物 ${indexPath}；请先运行 Hugo 生产构建`);
    return;
  }

  const match = html.match(/<script\b(?=[^>]*\bid\s*=\s*["']?home-quotes["']?(?=\s|>))[^>]*>([\s\S]*?)<\/script\s*>/i);
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
  if (!Array.isArray(data)) {
    fail(`#home-quotes 一次解析后应为数组，实际为 ${typeof data}（可能被双重编码）`);
    return;
  }
  if (!data.length) {
    fail("#home-quotes 数组不能为空");
    return;
  }
  if (!data.every((quote) => quote && typeof quote.text === "string"
    && quote.text.trim() && typeof quote.source === "string")) {
    fail("每个句子项都必须包含非空 text 字符串和 source 字符串");
    return;
  }
  ok(`#home-quotes 一次解析得到 ${data.length} 条有效句子`);
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
  const waiting = await run({
    wait: 300,
    backgrounds: [{ src: "/home/backgrounds/test.jpg" }]
  }, quotesFetch([{ text: "随机句子", source: "" }]));
  const pending = elsRef;
  await waiting;
  if (!pending.text.textContent) fail("内联句子数据应立即开始显示");
  else ok(`句子立即显示：${pending.text.textContent}`);
  if (pending.host.classList.contains("is-loading")) fail("有内联句子数据时句子区仍隐藏");
  else ok("句子区没有等待背景图 load");
  if (waiting.backgroundImage.src !== "/home/backgrounds/test.jpg") {
    fail("随机背景没有在后台开始加载");
  } else ok("随机背景请求已启动且未等待其完成");

  console.log("0.1 移动端变体、最近背景避让与 WebP 回退");
  const backgroundStore = {
    "home-background-recent": JSON.stringify(["recent-a.jpg", "recent-b.jpg"])
  };
  const backgroundResult = await run({
    wait: 300,
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

  console.log("A. 打字过程（逐帧观察文本长度）");
  const long = { text: "这是一句用来观察打字过程的话。", source: "《测试》· 某人" };
  let initialText = null;
  let initialDelay = null;
  const typing = await run({
    fakeTimers: true,
    width: 3000,
    backgrounds: [{ src: "/home/backgrounds/pending.jpg" }],
    onInit: ({ els, clock }) => {
      initialText = els.text.textContent;
      initialDelay = clock.scheduledDelays[0];
    }
  }, quotesFetch([long]));
  if (initialText !== "") fail(`打字开始前文本必须为空，实际：[${initialText}]`);
  else ok("打字开始前文本为空");
  if (initialDelay !== 220) fail(`首次打字延迟应为 220ms，实际 ${initialDelay}ms`);
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
  if (typing.els.source.textContent !== "《测试》· 某人") fail("出处未显示");
  else ok(`出处显示：${typing.els.source.textContent}`);

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
  console.log(`      文本 = [${empty.els.text.textContent}]`);
  if (empty.els.text.textContent !== "building small things, thinking about large things.") {
    fail("空句子库时应显示完整兜底句");
  } else ok("保留兜底句，页面不空白");
  if (!empty.warns.some((w) => w.includes("quotes"))) fail("空句子库时应留一条 console.warn");
  else ok(`console.warn：${empty.warns[0].slice(0, 50)}`);

  console.log();
  console.log("D. error：内联数据无效");
  const err = await run({ wait: 400 }, "{");
  console.log(`      文本 = [${err.els.text.textContent}]`);
  if (err.els.text.textContent !== "building small things, thinking about large things.") {
    fail("请求失败时应显示完整兜底句");
  } else ok("请求失败时显示兜底句");
  if (!err.warns.some((w) => w.includes("加载失败"))) fail("失败时应留一条 console.warn");
  else ok(`console.warn：${err.warns[0].slice(0, 60)}`);

  console.log();
  console.log("E. 格式不对（缺 quotes 数组）");
  const badShape = await run({ wait: 400 }, JSON.stringify({ groups: [] }));
  if (!badShape.warns.some((w) => w.includes("加载失败"))) fail("缺 quotes 时应走 error 分支");
  else ok("走 error 分支并保留原句");

  console.log();
  console.log("F. prefers-reduced-motion：直接显示整句");
  const rm = await run({ wait: 250, reduceMotion: true }, quotesFetch([long]));
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
  const n = Array.from(cut.els.text.textContent).length;
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
