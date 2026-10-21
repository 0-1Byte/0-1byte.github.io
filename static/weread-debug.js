(() => {
  "use strict";

  const fields = Object.fromEntries(
    Array.from(document.querySelectorAll("[data-weread-debug]"))
      .map((element) => [element.dataset.wereadDebug, element]),
  );
  const retryButton = document.querySelector("[data-weread-debug-retry]");
  const requestTimeoutMs = 12000;
  const expectedKeys = ["author", "chapter", "source", "source_type", "text"];
  let requestInProgress = false;

  function setField(name, value) {
    if (fields[name]) fields[name].textContent = value;
  }

  function classifyQuote(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value).sort();
    if (keys.length !== expectedKeys.length
      || keys.some((key, index) => key !== expectedKeys[index])) return false;
    return value.source_type === "weread"
      && typeof value.text === "string"
      && value.text.trim().length > 0
      && value.text.length <= 20000
      && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value.text)
      && ["source", "author", "chapter"].every((key) =>
        typeof value[key] === "string" && value[key].length <= 2000);
  }

  function failureForStatus(status) {
    if (status === 429) return "HTTP 429：请求过于频繁，请稍后再试";
    if (status === 503) return "HTTP 503：服务暂不可用";
    return `其他 HTTP 错误：${status}`;
  }

  async function runRequest() {
    if (requestInProgress) return;
    requestInProgress = true;
    retryButton.disabled = true;

    setField("request", "已发起");
    setField("http", "等待响应");
    setField("duration", "计时中");
    setField("json", "未检查");
    setField("validated", "未检查");
    setField("reason", "正在请求");
    setField("failure", "正在请求公开接口");

    const configuredBase = String(window.WEREAD_SYNC_API_BASE || "").replace(/\/+$/, "");
    let endpoint;
    try {
      const base = new URL(configuredBase);
      if (base.protocol !== "https:" || base.username || base.password
        || base.search || base.hash) throw new TypeError("Invalid Worker URL");
      endpoint = new URL("/public/quote", base);
      setField("api", `已配置：${base.hostname}`);
    } catch (_) {
      setField("api", configuredBase ? "地址格式无效" : "未配置");
      setField("request", "未发起");
      setField("http", "—");
      setField("duration", "—");
      setField("reason", "Worker 配置缺失或无效");
      setField("failure", "无法发起请求：Worker 配置缺失或无效");
      requestInProgress = false;
      retryButton.disabled = false;
      return;
    }

    const startedAt = performance.now();
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, requestTimeoutMs);

    try {
      const response = await fetch(endpoint.href, {
        method: "GET",
        mode: "cors",
        credentials: "omit",
        cache: "no-store",
        referrerPolicy: "no-referrer",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      setField("http", String(response.status));
      if (!response.ok) {
        setField("reason", failureForStatus(response.status));
        setField("failure", failureForStatus(response.status));
        return;
      }

      const contentType = response.headers.get("content-type") || "";
      if (!/application\/(?:[\w.+-]+\+)?json\b/i.test(contentType)) {
        setField("reason", "内容类型错误：响应不是 JSON");
        setField("failure", "内容类型错误");
        return;
      }

      let body;
      try {
        body = await response.json();
        setField("json", "正确");
      } catch (_) {
        setField("json", "错误");
        setField("reason", "JSON 错误：响应无法解析");
        setField("failure", "JSON 格式错误");
        return;
      }

      if (!classifyQuote(body)) {
        setField("validated", "未通过");
        setField("reason", "数据校验失败：响应结构不符合预期");
        setField("failure", "WeRead 数据校验失败");
        return;
      }

      setField("validated", "通过");
      setField("reason", "无");
      setField("failure", "请求成功，WeRead 数据校验通过");
    } catch (_) {
      setField("http", "无响应");
      if (timedOut) {
        setField("reason", "超时：请求超过 12 秒");
        setField("failure", "请求超时");
      } else {
        setField("reason", "网络/CORS 错误：浏览器无法读取 Worker 响应");
        setField("failure", "网络/CORS 错误");
      }
    } finally {
      window.clearTimeout(timeoutId);
      setField("duration", `${Math.round(performance.now() - startedAt)} 毫秒`);
      requestInProgress = false;
      retryButton.disabled = false;
    }
  }

  setField("script", "已执行");
  setField("failure", "诊断脚本已运行，准备请求");
  retryButton.disabled = false;
  retryButton.addEventListener("click", runRequest);
  runRequest();
})();
