(() => {
  "use strict";

  const apiBase = String(window.WEREAD_SYNC_API_BASE || "").replace(/\/+$/, "");
  const page = document.querySelector(".thoughts-page");
  if (!page) return;

  const grid = page.querySelector(".thoughts-grid");
  const status = document.getElementById("thoughts-status");
  const retryButton = document.getElementById("thoughts-retry");
  const addButton = document.getElementById("thoughts-add");
  const logoutButton = document.getElementById("thoughts-logout");
  const dialog = document.getElementById("thoughts-dialog");
  const form = document.getElementById("thoughts-form");
  const title = document.getElementById("thoughts-dialog-title");
  const contentField = document.getElementById("thoughts-content");
  const dateToggle = document.getElementById("thoughts-date-toggle");
  const dateField = document.getElementById("thoughts-date");
  const dateLabel = document.getElementById("thoughts-date-label");
  const formError = document.getElementById("thoughts-form-error");
  const saveButton = document.getElementById("thoughts-save");
  const cancelButton = document.getElementById("thoughts-cancel");

  let thoughts = [];
  let csrfToken = "";
  let isAdmin = false;
  let editingId = "";
  let originalContent = "";
  let originalDate = "";
  let dateIsExplicit = false;

  function setStatus(message, failed = false) {
    status.textContent = message;
    status.dataset.state = failed ? "error" : "ready";
    retryButton.hidden = !failed;
  }

  function isValidDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (year < 1 || month < 1 || month > 12) return false;
    const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return day >= 1 && day <= days[month - 1];
  }

  function tokyoToday() {
    const parts = new Intl.DateTimeFormat("en", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).formatToParts(new Date());
    const date = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    return `${date.year}-${date.month}-${date.day}`;
  }

  function validThought(value) {
    return value && typeof value.id === "string"
      && typeof value.content === "string"
      && isValidDate(value.date)
      && typeof value.created_at === "string"
      && typeof value.updated_at === "string";
  }

  function stableHash(value) {
    let hash = 2166136261;
    for (const character of value) {
      hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
    }
    return hash >>> 0;
  }

  function makeOperation(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      handler();
    });
    return button;
  }

  function renderThoughts() {
    const sorted = [...thoughts].sort((left, right) => (
      right.date.localeCompare(left.date)
      || Date.parse(right.created_at) - Date.parse(left.created_at)
      || left.id.localeCompare(right.id)
    ));
    grid.replaceChildren();

    for (const thought of sorted) {
      const note = document.createElement("article");
      note.className = "thoughts-note";
      note.dataset.noteId = thought.id;
      note.dataset.tone = String(stableHash(thought.id) % 4);
      note.style.setProperty("--note-rotation", `${((stableHash(thought.id) % 9) - 4) * 0.18}deg`);

      const text = document.createElement("div");
      text.className = "thoughts-note-text";
      text.textContent = thought.content;

      const date = document.createElement("time");
      date.className = "thoughts-note-date";
      date.dateTime = thought.date;
      date.textContent = thought.date.replaceAll("-", "/");

      note.append(text);
      if (isAdmin) {
        const operations = document.createElement("div");
        operations.className = "thoughts-note-operations";
        operations.append(
          makeOperation("编辑便签", "thoughts-note-edit", () => openEditor(thought)),
          makeOperation("删除便签", "thoughts-note-delete", () => deleteThought(thought))
        );
        note.append(operations);
      }
      note.append(date);
      grid.append(note);
    }
  }

  async function responseJson(response) {
    try {
      return await response.json();
    } catch (_) {
      return {};
    }
  }

  function errorMessage(error) {
    return {
      authentication_required: "登录状态已失效，请重新登录后再试。",
      csrf_rejected: "安全校验已过期，请刷新页面后重试。",
      invalid_content_type: "请求格式无效，请重试。",
      invalid_thought: "正文不能为空，日期必须有效，正文不能超过 6000 个字符。",
      thought_not_found: "这条便签已不存在，请刷新页面。",
      thoughts_unavailable: "便签服务暂时不可用，请稍后重试。",
      thoughts_service_unavailable: "便签服务尚未配置，请稍后重试。",
      thought_write_failed: "保存失败，数据未更改。请稍后重试。"
    }[error] || "操作失败，数据未更改。请检查连接后重试。";
  }

  async function loadThoughts() {
    if (!apiBase) {
      setStatus("便签服务地址未配置。", true);
      return;
    }
    retryButton.hidden = true;
    setStatus("正在加载…");
    try {
      const response = await fetch(`${apiBase}/public/thoughts`, {
        headers: { Accept: "application/json" },
        credentials: "omit",
        cache: "no-store"
      });
      const body = await responseJson(response);
      if (!response.ok) throw new Error(body.error || `http_${response.status}`);
      if (!Array.isArray(body.thoughts) || !body.thoughts.every(validThought)) {
        throw new Error("invalid_response");
      }
      thoughts = body.thoughts;
      renderThoughts();
      setStatus(thoughts.length ? "" : "目前没有便签。");
    } catch (error) {
      setStatus(errorMessage(error.message), true);
    }
  }

  async function getSession() {
    if (!apiBase) return;
    try {
      const response = await fetch(`${apiBase}/api/session`, {
        headers: { Accept: "application/json" },
        credentials: "include",
        cache: "no-store"
      });
      if (response.status === 401) return;
      const body = await responseJson(response);
      if (!response.ok || body.authenticated !== true || typeof body.csrf !== "string") {
        throw new Error(body.error || `http_${response.status}`);
      }
      csrfToken = body.csrf;
      isAdmin = true;
      page.classList.add("is-admin");
      logoutButton.hidden = false;
      renderThoughts();
    } catch (_) {
      setStatus("无法确认管理登录状态；新增便签时需要重新登录。", true);
    }
  }

  function setDateVisible(visible) {
    dateIsExplicit = visible;
    dateField.hidden = !visible;
    dateLabel.hidden = !visible;
    dateToggle.textContent = visible ? "取消修改日期" : "修改日期";
    dateToggle.setAttribute("aria-expanded", String(visible));
  }

  function openEditor(thought = null) {
    if (!isAdmin) return;
    editingId = thought?.id || "";
    originalContent = thought?.content || "";
    originalDate = thought?.date || "";
    title.textContent = editingId ? "编辑便签" : "新增便签";
    contentField.value = originalContent;
    dateField.value = originalDate || tokyoToday();
    formError.hidden = true;
    formError.textContent = "";
    saveButton.disabled = false;
    setDateVisible(false);
    dialog.showModal();
    contentField.focus();
  }

  function beginLogin() {
    if (!apiBase) {
      setStatus("便签服务地址未配置。", true);
      return;
    }
    const login = new URL("/auth/login", apiBase);
    login.searchParams.set("return_to", "/thoughts/");
    window.location.assign(login.toString());
  }

  async function adminRequest(path, method, body) {
    const headers = { Accept: "application/json", "X-CSRF-Token": csrfToken };
    const options = { method, credentials: "include", cache: "no-store", headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(`${apiBase}${path}`, options);
    const result = await responseJson(response);
    if (!response.ok) {
      if (response.status === 401) {
        isAdmin = false;
        csrfToken = "";
        page.classList.remove("is-admin");
        logoutButton.hidden = true;
        renderThoughts();
      }
      throw new Error(result.error || `http_${response.status}`);
    }
    return result;
  }

  async function saveThought(event) {
    event.preventDefault();
    if (saveButton.disabled || !isAdmin) return;
    const text = contentField.value;
    if (!text.trim()) {
      formError.textContent = "正文不能为空。";
      formError.hidden = false;
      contentField.focus();
      return;
    }

    const body = {};
    if (!editingId || text !== originalContent) body.content = text;
    if (dateIsExplicit) {
      if (!dateField.value || !isValidDate(dateField.value)) {
        formError.textContent = "请选择有效日期。";
        formError.hidden = false;
        dateField.focus();
        return;
      }
      if (dateField.value !== originalDate) body.date = dateField.value;
      if (!editingId && dateField.value === tokyoToday()) body.date = dateField.value;
    }
    if (editingId && Object.keys(body).length === 0) {
      dialog.close();
      return;
    }
    saveButton.disabled = true;
    formError.hidden = true;
    try {
      const result = editingId
        ? await adminRequest(`/admin/thoughts/${encodeURIComponent(editingId)}`, "PATCH", body)
        : await adminRequest("/admin/thoughts", "POST", body);
      if (!validThought(result.thought)) throw new Error("invalid_response");
      if (editingId) {
        thoughts = thoughts.map((thought) => (
          thought.id === editingId ? result.thought : thought
        ));
      } else {
        thoughts.push(result.thought);
      }
      renderThoughts();
      dialog.close();
      setStatus("已保存。");
    } catch (error) {
      formError.textContent = errorMessage(error.message);
      formError.hidden = false;
    } finally {
      saveButton.disabled = false;
    }
  }

  async function deleteThought(thought) {
    if (!isAdmin || !window.confirm("确定删除这条便签吗？此操作无法撤销。")) return;
    try {
      await adminRequest(`/admin/thoughts/${encodeURIComponent(thought.id)}`, "DELETE");
      thoughts = thoughts.filter((item) => item.id !== thought.id);
      renderThoughts();
      setStatus(thoughts.length ? "已删除。" : "目前没有便签。");
    } catch (error) {
      setStatus(errorMessage(error.message), true);
    }
  }

  addButton.addEventListener("click", () => {
    if (isAdmin) openEditor();
    else beginLogin();
  });
  retryButton.addEventListener("click", loadThoughts);
  dateToggle.addEventListener("click", () => {
    setDateVisible(!dateIsExplicit);
    if (dateIsExplicit) dateField.focus();
  });
  cancelButton.addEventListener("click", () => dialog.close());
  form.addEventListener("submit", saveThought);
  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      await adminRequest("/api/logout", "POST");
      isAdmin = false;
      csrfToken = "";
      page.classList.remove("is-admin");
      logoutButton.hidden = true;
      renderThoughts();
      setStatus("已退出。");
    } catch (error) {
      setStatus(errorMessage(error.message), true);
    } finally {
      logoutButton.disabled = false;
    }
  });

  loadThoughts();
  getSession();
})();
