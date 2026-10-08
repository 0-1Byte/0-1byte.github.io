/* 在 Node 里跑真实的 /quotes.js，验证打字机行为：
     A. 打字：逐字增加，不是一次性显示
     B. 完成后光标变暗（is-done）
     C. 出处显示 / 隐藏
     D. empty：句子库为空 -> 兜底句 + console.warn
     E. error：请求失败 -> 显示兜底句 + console.warn（不打扰访客）
     F. prefers-reduced-motion -> 直接显示整句
     G. 超长句子截断
     H. 尽量避开上一句（localStorage 记忆）
   脚本取自 static/quotes.js。 */
const fs = require("fs");
const path = require("path");

const ROOT = "D:/AAA_RELOAD/my-blog";
const STATIC = path.join(ROOT, "static");
const src = fs.readFileSync(path.join(STATIC, "quotes.js"), "utf8");

let problems = 0;
const fail = (m) => { problems++; console.log("      ✗ " + m); };
const ok = (m) => console.log("      " + m);

function makeEl(id, cls) {
  const el = {
    id, _classes: new Set(cls ? cls.split(" ") : []),
    textContent: "", hidden: false, _handlers: {}, _attrs: {},
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
    addEventListener(t, fn) { (el._handlers[t] ||= []).push(fn); }
  };
  return el;
}

let elsRef = {};

function setup(opts) {
  const host = makeEl("home-focus", "home-focus is-loading");
  const text = makeEl("home-focus-text");
  const caret = makeEl("home-focus-caret");
  const source = makeEl("home-focus-source");
  text.textContent = opts.serverText || "";
  elsRef = { host, text, caret, source };

  const doc = {
    getElementById: (id) => (id === "home-focus" ? host : null),
    querySelector: (sel) => (sel === "[data-quote-source]" ? source : null),
    addEventListener() {},
    documentElement: { dataset: {} },
    hidden: false
  };
  const win = {
    matchMedia: (q) => ({ matches: opts.reduceMotion === true && q.includes("reduced-motion") })
  };
  return { doc, win, els: elsRef };
}

async function run(opts, fetchImpl) {
  const env = setup(opts);
  const store = opts.store || {};
  const warns = [];
  const con = { ...console, warn: (...a) => warns.push(a.map(String).join(" ")), error: () => {} };

  const savedDoc = global.document, savedWin = global.window, savedLs = global.localStorage;
  global.document = env.doc;
  global.window = env.win;
  global.localStorage = {
    setItem(k, v) { store[k] = v; },
    getItem(k) { return store[k] === undefined ? null : store[k]; }
  };
  global.AbortController = function () { this.signal = {}; this.abort = () => {}; };

  try {
    new Function("document", "window", "fetch", "console", "localStorage",
      "AbortController", "setTimeout", "clearTimeout", src)(
      env.doc, env.win, fetchImpl, con, global.localStorage,
      global.AbortController, setTimeout, clearTimeout);
    await new Promise((r) => setTimeout(r, opts.wait || 300));
  } finally {
    global.document = savedDoc; global.window = savedWin; global.localStorage = savedLs;
  }
  return { ...env, warns, store };
}

const quotesFetch = (list) => async () => ({
  ok: true, status: 200, json: async () => ({ groups: [], standalone: [], quotes: list })
});

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
  console.log("0. loading：数据就绪前保持隐藏且不含固定首句");
  let releaseFetch;
  const waiting = run({ wait: 50 }, () => new Promise((resolve) => { releaseFetch = resolve; }));
  await new Promise((r) => setTimeout(r, 20));
  const pending = elsRef;
  if (pending.text.textContent) fail("数据未就绪时句子区不应含有可见文案");
  else ok("数据未就绪时句子内容为空");
  if (!pending.host.classList.contains("is-loading")) fail("数据未就绪时句子区应保持隐藏");
  else ok("数据未就绪时句子区保持隐藏");
  releaseFetch(await quotesFetch([{ text: "随机句子", source: "" }])());
  await waiting;
  if (pending.host.classList.contains("is-loading")) fail("数据就绪后句子区未显示");
  else ok("数据就绪后句子区显示");

  console.log("A. 打字过程（逐帧观察文本长度）");
  const long = { text: "这是一句用来观察打字过程的话。", source: "《测试》· 某人" };
  // 逐段观察：在打字中途取一次，结束时再取一次
  const typing = await run({ wait: 500 }, quotesFetch([long]));
  const mid = typing.els.text.textContent;
  await new Promise((r) => setTimeout(r, 1500));
  const end = typing.els.text.textContent;
  console.log(`      500ms 时文本 = [${mid}]  长度 ${Array.from(mid).length}`);
  console.log(`      2s 后文本   = [${end}]  长度 ${Array.from(end).length}`);
  if (!end) fail("最终没有打出任何文字");
  if (Array.from(mid).length >= Array.from(end).length && end) {
    fail("500ms 时就已打完，说明不是逐字输出");
  }
  if (end !== long.text) fail(`最终文本与句子不一致：[${end}]`);
  ok("逐字输出，最终完整");
  if (!typing.els.caret._classes.has("is-done")) fail("打完后光标未标记 is-done");
  else ok("打完后光标变暗（is-done）");
  if (typing.els.source.textContent !== "《测试》· 某人") fail("出处未显示");
  else ok(`出处显示：${typing.els.source.textContent}`);

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
  console.log("D. error：请求失败");
  const err = await run({ wait: 400 }, async () => { throw new Error("network down"); });
  console.log(`      文本 = [${err.els.text.textContent}]`);
  if (err.els.text.textContent !== "building small things, thinking about large things.") {
    fail("请求失败时应显示完整兜底句");
  } else ok("请求失败时显示兜底句");
  if (!err.warns.some((w) => w.includes("加载失败"))) fail("失败时应留一条 console.warn");
  else ok(`console.warn：${err.warns[0].slice(0, 60)}`);

  console.log();
  console.log("E. 格式不对（缺 quotes 数组）");
  const badShape = await run({ wait: 400 }, async () => ({
    ok: true, status: 200, json: async () => ({ groups: [] })
  }));
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
  console.log("G. 超长句子截断到 140 字符");
  const huge = { text: "字".repeat(300), source: "" };
  const cut = await run({ wait: 300, reduceMotion: true }, quotesFetch([huge]));
  const n = Array.from(cut.els.text.textContent).length;
  console.log(`      显示长度 = ${n}`);
  if (n !== 140) fail(`应截断到 140，实际 ${n}`);
  else ok("截断到 140");

  console.log();
  console.log("H. 尽量避开上一句");
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
