/* 在 Node 里跑真实的 /quotes.js，验证打字机行为：
     A. 打字：逐字增加，不是一次性显示
     B. 完成后光标变暗（is-done）
     C. 出处显示 / 隐藏
     D. empty：句子库为空 -> 兜底句 + console.warn
     E. error：请求失败 -> 保留页面上的句子 + console.warn（不打扰访客）
     F. prefers-reduced-motion -> 直接显示整句
     G. 超长句子截断
     H. 尽量避开上一句（localStorage 记忆）
   脚本取自构建产物。 */
const fs = require("fs");
const path = require("path");

const ROOT = "D:/AAA_RELOAD/my-blog";
const PUB = path.join(ROOT, "public");
const src = fs.readFileSync(path.join(PUB, "quotes.js"), "utf8");

let problems = 0;
const fail = (m) => { problems++; console.log("      ✗ " + m); };
const ok = (m) => console.log("      " + m);

function makeEl(id, cls) {
  const el = {
    id, _classes: new Set(cls ? cls.split(" ") : []),
    textContent: "", hidden: false, _handlers: {},
    classList: {
      add(c) { el._classes.add(c); },
      remove(c) { el._classes.delete(c); },
      contains(c) { return el._classes.has(c); }
    },
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
  const host = makeEl("home-focus", "home-focus");
  const text = makeEl("home-focus-text");
  const caret = makeEl("home-focus-caret");
  const source = makeEl("home-focus-source");
  text.textContent = opts.serverText || "building small things,";
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

(async () => {
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
  if (empty.els.text.textContent !== "building small things,") {
    fail("空句子库时应保留页面上的兜底句");
  } else ok("保留兜底句，页面不空白");
  if (!empty.warns.some((w) => w.includes("quotes"))) fail("空句子库时应留一条 console.warn");
  else ok(`console.warn：${empty.warns[0].slice(0, 50)}`);

  console.log();
  console.log("D. error：请求失败");
  const err = await run({ wait: 400 }, async () => { throw new Error("network down"); });
  console.log(`      文本 = [${err.els.text.textContent}]`);
  if (err.els.text.textContent !== "building small things,") {
    fail("请求失败时应保留页面上的句子");
  } else ok("保留页面上的句子，不打扰访客");
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

  console.log();
  console.log(`合计问题: ${problems}`);
  process.exit(problems ? 1 : 0);
})();
