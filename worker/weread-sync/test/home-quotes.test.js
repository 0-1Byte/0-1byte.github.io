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

function browserFor(fetchImpl, randomValue = 0.9) {
  const warnings = [];
  const text = { textContent: "" };
  const source = {
    textContent: "",
    hidden: true,
    setAttribute() {},
    removeAttribute() {}
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
    WEREAD_SYNC_API_BASE: USER_AGENT_ORIGIN,
    location: { hostname: "0-1byte.github.io", search: "" },
    matchMedia(query) {
      return { matches: query === "(prefers-reduced-motion: reduce)" };
    },
    addEventListener() {}
  };
  const context = {
    AbortController,
    URLSearchParams,
    Intl,
    Math: math,
    Date,
    JSON,
    String,
    Array,
    Set,
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
  return { text, source, warnings };
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
  assert.equal(browser.text.textContent.replace(/\s/g, ""), "RemoteWeReadquote");
  assert.equal(browser.warnings.length, 0);
});

test("homepage keeps the manual quote and diagnoses a Worker timeout", async () => {
  const browser = browserFor(() => new Promise(() => {}));
  await tick();
  assert.equal(browser.text.textContent.replace(/\s/g, ""), "Manualfallbackquote");
  assert.deepEqual(browser.warnings[0], [
    "[quotes] WeRead request failed:",
    "timeout"
  ]);
});

test("homepage keeps the manual quote and diagnoses HTTP and malformed JSON responses", async (t) => {
  await t.test("HTTP status", async () => {
    const browser = browserFor(async () => response(503, ""));
    await tick();
    assert.equal(browser.text.textContent.replace(/\s/g, ""), "Manualfallbackquote");
    assert.deepEqual(browser.warnings[0], [
      "[quotes] WeRead request failed: http_status",
      503
    ]);
  });
  await t.test("malformed JSON", async () => {
    const browser = browserFor(async () => response(200, "{"));
    await tick();
    assert.equal(browser.text.textContent.replace(/\s/g, ""), "Manualfallbackquote");
    assert.deepEqual(browser.warnings[0], [
      "[quotes] WeRead request failed:",
      "invalid_json"
    ]);
  });
});

test("homepage keeps the manual quote and diagnoses network failures without logging details", async () => {
  const browser = browserFor(async () => {
    throw new TypeError("sensitive request detail");
  });
  await tick();
  assert.equal(browser.text.textContent.replace(/\s/g, ""), "Manualfallbackquote");
  assert.deepEqual(browser.warnings[0], [
    "[quotes] WeRead request failed:",
    "network_error"
  ]);
  assert.equal(JSON.stringify(browser.warnings).includes("sensitive"), false);
});

test("random selection can still show the manual quote without requesting WeRead", async () => {
  let called = false;
  const browser = browserFor(async () => {
    called = true;
    return response(200, JSON.stringify(remoteQuote));
  }, 0.1);
  await tick();
  assert.equal(called, false);
  assert.equal(browser.text.textContent.replace(/\s/g, ""), "Manualfallbackquote");
});
