import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const quoteScript = await readFile(path.join(root, "static/quotes.js"), "utf8");
const USER_AGENT_ORIGIN = "https://weread-sync-console.weread-chen.workers.dev";
const manualQuote = {
  text: "Manual fallback quote",
  source_type: "manual",
  source: "Manual source"
};
const remoteQuote = {
  text: "Remote WeRead quote",
  source_type: "weread",
  source: "Synthetic book",
  author: "Synthetic author",
  chapter: "Synthetic chapter"
};

function browserFor(fetchImpl, { randomValue = 0.9, search = "", apiBase = USER_AGENT_ORIGIN } = {}) {
  const warnings = [];
  const text = { textContent: "" };
  const source = {
    textContent: "",
    hidden: true,
    setAttribute() {},
    removeAttribute() {}
  };
  const debugValues = new Map();
  const retryButton = { addEventListener(_name, callback) { this.callback = callback; } };
  const debugPanel = {
    hidden: true,
    querySelectorAll() {
      return ["version", "api", "request", "http", "duration", "validated", "failure"]
        .map((key) => ({
          getAttribute() { return key; },
          set textContent(value) { debugValues.set(key, value); }
        }));
    },
    querySelector(selector) {
      return selector === "[data-weread-debug-retry]" ? retryButton : null;
    }
  };
  const classList = { add() {}, remove() {} };
  const host = {
    clientWidth: 320,
    classList,
    querySelector(selector) {
      return selector === "[data-quote-text]" ? text : { classList };
    },
    closest() { return null; }
  };
  const document = {
    hidden: false,
    getElementById(id) {
      if (id === "home-focus") return host;
      if (id === "home-quotes") return { textContent: JSON.stringify({ manual: [manualQuote] }) };
      if (id === "weread-debug") return debugPanel;
      return null;
    },
    querySelector(selector) {
      return selector === "[data-quote-source]" ? source : null;
    },
    createElement() { return null; },
    addEventListener() {}
  };
  const math = Object.create(Math);
  math.random = () => randomValue;
  const localStorage = { getItem() { return ""; }, setItem() {} };
  const window = {
    WEREAD_SYNC_API_BASE: apiBase,
    location: { hostname: "0-1byte.github.io", search },
    matchMedia(query) {
      return { matches: query === "(prefers-reduced-motion: reduce)" };
    },
    addEventListener() {}
  };
  const context = {
    AbortController,
    URL,
    URLSearchParams,
    Intl,
    Math: math,
    Date,
    JSON,
    String,
    Array,
    Set,
    Object,
    Promise,
    navigator: { hardwareConcurrency: 8 },
    document,
    window,
    localStorage,
    fetch: fetchImpl,
    console: { warn(...args) { warnings.push(args); } },
    setInterval() { return 1; },
    clearInterval() {},
    setTimeout(callback, delay) {
      return globalThis.setTimeout(callback, delay >= 8000 ? 5 : delay);
    },
    clearTimeout
  };
  vm.runInNewContext(quoteScript, context);
  return { text, source, warnings, debugPanel, debugValues, retryButton };
}

function response(status, body, contentType = "application/json") {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        if (name.toLowerCase() === "content-type") return contentType;
        if (name.toLowerCase() === "content-length") return null;
        return null;
      }
    },
    async text() { return body; }
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 15));
const visibleText = (browser) => browser.text.textContent.replace(/\s/g, "");

test("homepage displays a validated Worker quote when the request succeeds", async () => {
  let requestUrl = "";
  const browser = browserFor(async (url, options) => {
    requestUrl = url;
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    return response(200, JSON.stringify(remoteQuote));
  });
  await tick();
  assert.equal(requestUrl, `${USER_AGENT_ORIGIN}/public/quote`);
  assert.equal(visibleText(browser), "RemoteWeReadquote");
  assert.equal(browser.warnings.length, 0);
});

test("diagnostic mode always requests, displays safe status, and supports retry", async () => {
  let calls = 0;
  const browser = browserFor(async () => {
    calls += 1;
    return response(200, JSON.stringify(remoteQuote));
  }, { randomValue: 0.1, search: "?wereadDebug=1" });
  await tick();
  assert.equal(calls, 1);
  assert.equal(visibleText(browser), "RemoteWeReadquote");
  assert.equal(browser.debugPanel.hidden, false);
  assert.equal(browser.debugValues.get("version"), "已加载 v12");
  assert.equal(browser.debugValues.get("api"), "已配置：weread-sync-console.weread-chen.workers.dev");
  assert.equal(browser.debugValues.get("request"), "已发起");
  assert.equal(browser.debugValues.get("http"), "200");
  assert.equal(browser.debugValues.get("validated"), "是");
  assert.equal(browser.debugValues.get("failure"), "无");
  assert.equal(JSON.stringify([...browser.debugValues.values()]).includes(remoteQuote.text), false);

  browser.retryButton.callback();
  await tick();
  assert.equal(calls, 2);
});

test("diagnostic mode distinguishes an unconfigured API from a failed request", async () => {
  let called = false;
  const browser = browserFor(async () => {
    called = true;
    return response(200, JSON.stringify(remoteQuote));
  }, { search: "?wereadDebug=1", apiBase: "" });
  await tick();
  assert.equal(called, false);
  assert.equal(visibleText(browser), "Manualfallbackquote");
  assert.equal(browser.debugValues.get("api"), "未配置");
  assert.equal(browser.debugValues.get("request"), "未发起");
  assert.equal(browser.debugValues.get("http"), "无");
  assert.equal(browser.debugValues.get("failure"), "API 地址未配置");
});

test("homepage keeps the manual quote and diagnoses timeout", async () => {
  const browser = browserFor(() => new Promise(() => {}), { search: "?wereadDebug=1" });
  await tick();
  assert.equal(visibleText(browser), "Manualfallbackquote");
  assert.equal(browser.debugValues.get("request"), "已发起");
  assert.equal(browser.debugValues.get("failure"), "请求超时");
  assert.equal(browser.warnings[0][1], "timeout");
});

test("diagnostic mode classifies HTTP 429, HTTP 503, and other HTTP errors", async (t) => {
  for (const [status, expected] of [[429, "HTTP 429 限流"], [503, "HTTP 503 服务暂不可用"], [502, "其他 HTTP 错误"]]) {
    await t.test(String(status), async () => {
      const browser = browserFor(async () => response(status, "not displayed"), {
        search: "?wereadDebug=1"
      });
      await tick();
      assert.equal(browser.debugValues.get("http"), String(status));
      assert.equal(browser.debugValues.get("failure"), expected);
      assert.equal(visibleText(browser), "Manualfallbackquote");
    });
  }
});

test("diagnostic mode identifies CORS/network failures without exposing error details", async () => {
  const browser = browserFor(async () => {
    throw new TypeError("sensitive response detail");
  }, { search: "?wereadDebug=1" });
  await tick();
  assert.equal(browser.debugValues.get("failure"), "网络/CORS 错误");
  assert.equal(visibleText(browser), "Manualfallbackquote");
  assert.equal(JSON.stringify(browser.warnings).includes("sensitive"), false);
});

test("diagnostic mode classifies content type, malformed JSON, and invalid quote data", async (t) => {
  const cases = [
    ["content type", response(200, "{}", "text/plain"), "内容类型错误"],
    ["invalid JSON", response(200, "{"), "JSON 格式错误"],
    ["invalid quote", response(200, JSON.stringify({ source_type: "manual", text: "not a WeRead quote" })),
      "WeRead 数据校验失败"]
  ];
  for (const [name, value, expected] of cases) {
    await t.test(name, async () => {
      const browser = browserFor(async () => value, { search: "?wereadDebug=1" });
      await tick();
      assert.equal(browser.debugValues.get("validated"), "否");
      assert.equal(browser.debugValues.get("failure"), expected);
      assert.equal(visibleText(browser), "Manualfallbackquote");
    });
  }
});

test("ordinary random selection still may choose manual without requesting WeRead", async () => {
  let called = false;
  const browser = browserFor(async () => {
    called = true;
    return response(200, JSON.stringify(remoteQuote));
  }, { randomValue: 0.1 });
  await tick();
  assert.equal(called, false);
  assert.equal(visibleText(browser), "Manualfallbackquote");
  assert.equal(browser.debugPanel.hidden, true);
});
