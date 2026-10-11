(() => {
  "use strict";

  const apiBase = String(window.WEREAD_SYNC_API_BASE || "").replace(/\/+$/, "");
  const auth = document.getElementById("auth");
  const dashboard = document.getElementById("dashboard");
  const feedback = document.getElementById("feedback");
  const triggerButton = document.getElementById("trigger");
  const stateLabel = {
    idle: "尚无任务",
    queued: "排队中",
    in_progress: "运行中",
    success: "成功",
    failure: "失败"
  };
  let csrfToken = "";
  let pollTimer = 0;
  let active = false;

  function showFeedback(message) {
    feedback.textContent = message;
  }

  function formatDate(value) {
    if (!value) return "尚无记录";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "尚无记录" : date.toLocaleString();
  }

  function setText(id, value) {
    document.getElementById(id).textContent = value;
  }

  async function api(path, options = {}) {
    return fetch(`${apiBase}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...(options.headers || {})
      }
    });
  }

  function renderStatus(data) {
    const state = Object.prototype.hasOwnProperty.call(stateLabel, data.state)
      ? data.state
      : "failure";
    const badge = document.getElementById("state-badge");
    badge.textContent = stateLabel[state];
    badge.className = `state state-${state}`;
    setText("stage", data.current_stage || (state === "success" ? "校验与发布完成" : "—"));
    setText("run-time", data.submitted_at ? formatDate(data.submitted_at) : "");
    const logs = document.getElementById("logs");
    if (typeof data.run_url === "string"
      && /^https:\/\/github\.com\/0-1byte\/0-1byte\.github\.io\/actions\/runs\/\d+$/.test(data.run_url)) {
      logs.href = data.run_url;
      logs.hidden = false;
    } else {
      logs.hidden = true;
      logs.removeAttribute("href");
    }

    const stats = data.stats;
    if (stats && typeof stats === "object") {
      setText("last-sync", formatDate(data.last_success_at));
      setText("books-read", Number.isSafeInteger(stats.read_books) ? String(stats.read_books) : "—");
      setText("quote-count", Number.isSafeInteger(stats.quotes) ? String(stats.quotes) : "—");
      setText("missing-author", Number.isSafeInteger(stats.missing_author) ? String(stats.missing_author) : "—");
      setText("missing-chapter", Number.isSafeInteger(stats.missing_chapter) ? String(stats.missing_chapter) : "—");
      const chapterIssues = (Number(stats.unmapped_chapters) || 0)
        + (Number(stats.ambiguous_chapter_ids) || 0);
      setText("chapter-issues", String(chapterIssues));
    }

    active = state === "queued" || state === "in_progress";
    triggerButton.disabled = active;
    if (state === "success") {
      setText("summary", "同步、数据校验与站点构建均已通过。数据提交后，GitHub Pages 将自动部署。");
    } else if (state === "failure") {
      setText("summary", "任务失败；正式数据不会因同步或验收失败而发布。查看安全运行摘要和 Actions 日志。");
    } else if (state === "queued" || state === "in_progress") {
      setText("summary", "任务状态来自 GitHub Actions；页面不会推测进度百分比。");
    } else {
      setText("summary", "运行状态由 GitHub Actions 实时提供。");
    }
  }

  async function poll() {
    if (!apiBase || apiBase.includes("REPLACE_WITH_WORKER_HOST")) {
      showFeedback("请先在控制台部署配置中填写 Worker 地址。");
      triggerButton.disabled = true;
      return;
    }
    try {
      const response = await api("/api/status");
      if (response.status === 401) {
        auth.hidden = false;
        dashboard.hidden = true;
        document.getElementById("login").href = `${apiBase}/auth/login`;
        showFeedback("需要先通过后端身份认证。");
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      renderStatus(data);
      showFeedback("");
      clearTimeout(pollTimer);
      if (active) pollTimer = setTimeout(poll, 10000);
    } catch (_) {
      showFeedback("无法读取任务状态；请检查 Worker 配置或稍后重试。");
      triggerButton.disabled = true;
      pollTimer = setTimeout(poll, 20000);
    }
  }

  async function initialize() {
    if (!apiBase || apiBase.includes("REPLACE_WITH_WORKER_HOST")) {
      auth.hidden = false;
      document.getElementById("login").hidden = true;
      dashboard.hidden = true;
      showFeedback("尚未配置 Worker 地址，控制台当前不可用。");
      return;
    }
    try {
      const response = await api("/api/session");
      if (response.status === 401) {
        auth.hidden = false;
        dashboard.hidden = true;
        document.getElementById("login").href = `${apiBase}/auth/login`;
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const session = await response.json();
      csrfToken = typeof session.csrf === "string" ? session.csrf : "";
      setText("login-name", session.login || "");
      auth.hidden = true;
      dashboard.hidden = false;
      triggerButton.disabled = false;
      await poll();
    } catch (_) {
      auth.hidden = false;
      dashboard.hidden = true;
      showFeedback("身份服务暂时不可用；没有启动任何任务。");
    }
  }

  triggerButton.addEventListener("click", async () => {
    if (active || !csrfToken) return;
    triggerButton.disabled = true;
    showFeedback("正在向 GitHub Actions 提交任务…");
    try {
      const response = await api("/api/trigger", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID()
        },
        body: "{}"
      });
      const result = await response.json().catch(() => ({}));
      if (response.status === 202 && result.accepted === true) {
        active = true;
        showFeedback("任务已提交；正在等待 GitHub Actions 确认启动。");
        await poll();
        return;
      }
      const message = {
        rate_limited: "触发过于频繁，请等待冷却时间结束。",
        run_already_active: "已有任务正在排队或运行。",
        authentication_required: "登录状态已失效，请重新登录。",
        csrf_rejected: "安全校验失败，请刷新页面后重试。"
      }[result.error] || "任务启动失败；没有报告为成功。";
      showFeedback(message);
      triggerButton.disabled = false;
    } catch (_) {
      showFeedback("未能确认任务是否提交；请先刷新状态，避免重复触发。");
      triggerButton.disabled = true;
    }
  });

  document.getElementById("logout").addEventListener("click", async () => {
    try {
      await api("/api/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken }
      });
    } finally {
      window.location.reload();
    }
  });

  initialize();
})();
