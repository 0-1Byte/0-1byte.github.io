(function () {
  "use strict";

  const core = window.ReadManagerCore;
  const elements = Object.fromEntries([
    "directory-label", "choose-directory", "reauthorize", "new-article", "status",
    "warnings", "warning-list", "article-list", "editor", "editor-title", "rename-warning",
    "article-form", "article-type", "article-weight", "article-title", "article-filename",
    "external-url", "external-fields", "local-fields", "article-author", "article-source",
    "article-source-url", "article-date", "article-body", "preview-body", "body-preview",
    "cancel-edit"
  ].map((id) => [id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), document.getElementById(id)]));

  const state = {
    directory: null,
    articles: [],
    files: new Set(),
    editing: null,
    initialForm: "",
    busy: false
  };

  function setStatus(message, kind) {
    elements.status.textContent = message;
    elements.status.className = `status${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(busy) {
    state.busy = busy;
    elements.chooseDirectory.disabled = busy;
    elements.reauthorize.disabled = busy;
    elements.newArticle.disabled = busy || !state.directory || Boolean(state.editing);
    elements.articleForm.querySelector('[type="submit"]').disabled = busy;
    elements.articleList.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
    if (!busy && state.directory) renderList();
  }

  function formValues() {
    const data = new FormData(elements.articleForm);
    return { ...Object.fromEntries(data.entries()), target: elements.articleType.value };
  }

  function serializeForm() {
    return JSON.stringify(formValues());
  }

  function hasUnsavedChanges() {
    return state.editing && serializeForm() !== state.initialForm;
  }

  async function confirmDiscard() {
    if (!hasUnsavedChanges()) return true;
    return window.confirm("当前编辑尚未保存。放弃这些修改吗？");
  }

  function permissionOptions() {
    return { mode: "readwrite" };
  }

  async function ensurePermission(request) {
    if (!state.directory) throw new Error("尚未选择文章目录。");
    let permission = await state.directory.queryPermission(permissionOptions());
    if (permission !== "granted" && request) {
      permission = await state.directory.requestPermission(permissionOptions());
    }
    if (permission !== "granted") {
      elements.reauthorize.hidden = false;
      throw new Error("文章目录权限未获授权。请点击「重新授权」后重试。");
    }
    elements.reauthorize.hidden = true;
  }

  async function rememberDirectory(handle) {
    if (!window.indexedDB) return;
    await new Promise((resolve, reject) => {
      const request = indexedDB.open("read-manager-directory", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("handles");
      request.onerror = () => reject(request.error || new Error("无法保存目录选择记录。"));
      request.onsuccess = () => {
        const transaction = request.result.transaction("handles", "readwrite");
        transaction.objectStore("handles").put(handle, "articles");
        transaction.oncomplete = () => { request.result.close(); resolve(); };
        transaction.onerror = () => { request.result.close(); reject(transaction.error); };
      };
    });
  }

  async function loadRememberedDirectory() {
    if (!window.indexedDB) return null;
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("read-manager-directory", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("handles");
      request.onerror = () => reject(request.error || new Error("无法读取上次目录选择记录。"));
      request.onsuccess = () => {
        const transaction = request.result.transaction("handles", "readonly");
        const get = transaction.objectStore("handles").get("articles");
        get.onsuccess = () => { request.result.close(); resolve(get.result || null); };
        get.onerror = () => { request.result.close(); reject(get.error); };
      };
    });
  }

  async function scanDirectory() {
    await ensurePermission(false);
    const result = await core.scanDirectory(state.directory);
    if (!result.files.has("_index.md")) {
      throw new Error("所选目录中没有 _index.md。请选择项目里的 content/read/articles 文件夹。");
    }
    state.articles = result.articles;
    state.files = result.files;
    renderList();
    renderWarnings(result.warnings);
    elements.directoryLabel.textContent = `已连接：${state.directory.name}`;
    elements.newArticle.disabled = false;
    if (result.warnings.length) {
      setStatus(`已读取 ${result.articles.length} 篇文章；另有 ${result.warnings.length} 个 Markdown 文件未识别，未对其作任何修改。`, "success");
    } else {
      setStatus(`已读取 ${result.articles.length} 篇文章。`, "success");
    }
  }

  function renderWarnings(warnings) {
    elements.warnings.hidden = warnings.length === 0;
    elements.warningList.replaceChildren();
    for (const item of warnings) {
      const line = document.createElement("div");
      line.textContent = `${item.name}：${item.warning}`;
      elements.warningList.append(line);
    }
  }

  function renderList() {
    elements.articleList.className = state.articles.length ? "" : "empty";
    elements.articleList.replaceChildren();
    if (!state.directory) {
      elements.articleList.textContent = "选择文章目录后显示内容。";
      return;
    }
    if (!state.articles.length) {
      elements.articleList.textContent = "目录中还没有可识别的文章。";
      return;
    }
    state.articles.forEach((record, index) => {
      const row = document.createElement("article");
      row.className = "article-row";
      const description = document.createElement("div");
      const title = document.createElement("div");
      title.className = "article-title";
      title.textContent = record.article.title;
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = record.article.target === "external" ? "外部文章" : "站内全文";
      title.append(badge);
      const meta = document.createElement("div");
      meta.className = "article-meta";
      meta.textContent = `${record.name} · weight ${record.article.weight}`;
      description.append(title, meta);
      const actions = document.createElement("div");
      actions.className = "row-actions";
      const up = actionButton("上移", () => moveArticle(index, -1), index === 0);
      const down = actionButton("下移", () => moveArticle(index, 1), index === state.articles.length - 1);
      const edit = actionButton("编辑", () => openEditor(record));
      const remove = actionButton("删除", () => deleteArticle(record), false, "danger");
      actions.append(up, down, edit, remove);
      row.append(description, actions);
      elements.articleList.append(row);
    });
  }

  function actionButton(label, action, disabled, extraClass) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = disabled || state.busy || Boolean(state.editing);
    if (extraClass) button.classList.add(extraClass);
    button.addEventListener("click", () => Promise.resolve().then(action).catch(showError));
    return button;
  }

  function toggleTypeFields() {
    const external = elements.articleType.value === "external";
    elements.externalFields.hidden = !external;
    elements.localFields.hidden = external;
    elements.externalUrl.required = external;
    elements.articleBody.required = !external;
  }

  function setForm(record) {
    elements.articleType.value = record ? record.article.target : "external";
    elements.articleType.disabled = Boolean(record);
    elements.articleTitle.value = record ? record.article.title : "";
    elements.articleFilename.value = record ? record.name : core.slugFromTitle("", new Date().toISOString().slice(0, 10), state.files);
    elements.articleWeight.value = record
      ? String(record.article.weight)
      : String(state.articles.reduce((max, item) => Math.max(max, item.article.weight), 0) + 10);
    elements.externalUrl.value = record ? record.article.externalUrl : "";
    elements.articleAuthor.value = record ? record.article.author : "";
    elements.articleSource.value = record ? record.article.source : "";
    elements.articleSourceUrl.value = record ? record.article.sourceUrl : "";
    elements.articleDate.value = record ? record.article.date : "";
    elements.articleBody.value = record ? record.article.body.replace(/^\r?\n/, "") : "";
    elements.articleBody.dataset.initialBody = elements.articleBody.value;
    elements.bodyPreview.textContent = "";
    elements.bodyPreview.hidden = true;
    toggleTypeFields();
  }

  function openEditor(record) {
    setForm(record || null);
    state.editing = record || { new: true };
    elements.editorTitle.textContent = record ? "编辑文章" : "新增文章";
    elements.renameWarning.hidden = true;
    elements.editor.hidden = false;
    elements.newArticle.disabled = true;
    state.initialForm = serializeForm();
    elements.editor.scrollIntoView({ behavior: "smooth", block: "start" });
    elements.articleTitle.focus();
  }

  async function closeEditor() {
    if (!await confirmDiscard()) return;
    elements.editor.hidden = true;
    state.editing = null;
    state.initialForm = "";
    elements.newArticle.disabled = !state.directory || state.busy;
    return true;
  }

  async function saveArticle(event) {
    event.preventDefault();
    if (!state.editing) return;
    setBusy(true);
    try {
      await ensurePermission(false);
      const values = formValues();
      core.validateFilename(values.filename);
      const editing = state.editing.new ? null : state.editing;
      const nextName = values.filename;
      const renaming = Boolean(editing && nextName !== editing.name);
      if (!editing && state.files.has(nextName.toLowerCase())) throw new Error("该文件名已存在，请换一个名称。");
      if (renaming) {
        if (state.files.has(nextName.toLowerCase())) throw new Error("目标文件名已存在，请换一个名称。");
        elements.renameWarning.hidden = false;
        const confirmed = window.confirm(
          `这会把 ${editing.name} 改名为 ${nextName}，站内文章 URL 会改变。\n如果已有页面或外部网站链接到旧地址，改名可能造成失效。确认继续吗？`
        );
        if (!confirmed) return;
      }
      if (editing && values.target !== editing.article.target) {
        throw new Error("编辑时不能更改文章类型。请保留原类型，避免丢失文章内容或 URL。");
      }
      if (editing) {
        await core.editArticle(state.directory, editing, nextName, values, state.files, elements.articleBody.dataset.initialBody);
      } else {
        await core.createArticle(state.directory, nextName, values, state.files);
      }
      elements.editor.hidden = true;
      state.editing = null;
      state.initialForm = "";
      await scanDirectory();
      setStatus(`已保存：${nextName}`, "success");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function deleteArticle(record) {
    const confirmed = window.confirm(
      `确定删除文章「${record.article.title}」吗？\n文件：${record.name}\n\n这会修改本地项目文件。删除前会在文章目录的 .read-manager-backups 文件夹中保存备份。`
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      await ensurePermission(false);
      await core.deleteArticle(state.directory, record);
      await scanDirectory();
      setStatus(`已删除「${record.article.title}」，备份保存在 .read-manager-backups。`, "success");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function moveArticle(index, direction) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= state.articles.length) return;
    setBusy(true);
    try {
      await ensurePermission(false);
      await core.reorderArticles(state.articles, index, direction);
      await scanDirectory();
      setStatus("文章顺序已保存到各文件的 weight 字段。", "success");
    } catch (error) {
      showError(error);
      await scanDirectory().catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  function showError(error) {
    setStatus(error && error.message ? error.message : String(error), "error");
  }

  async function chooseDirectory() {
    if (!("showDirectoryPicker" in window)) {
      setStatus("此浏览器不支持目录访问 API。请使用随附的「Start Read Manager.cmd」启动器，再用最新版 Chrome 或 Edge 打开。", "error");
      return;
    }
    try {
      if (!await closeEditor()) return;
      const handle = await window.showDirectoryPicker({ id: "read-articles", mode: "readwrite" });
      state.directory = handle;
      await ensurePermission(true);
      let rememberError = null;
      try {
        await rememberDirectory(handle);
      } catch (error) {
        rememberError = error;
      }
      await scanDirectory();
      if (rememberError) {
        setStatus(`已读取文章目录。本次授权可正常使用，但浏览器未能记住目录：${rememberError.message}`, "error");
      }
    } catch (error) {
      if (error.name !== "AbortError") showError(error);
    }
  }

  async function reauthorize() {
    try {
      await ensurePermission(true);
      await scanDirectory();
    } catch (error) {
      showError(error);
    }
  }

  async function restoreDirectory() {
    try {
      const handle = await loadRememberedDirectory();
      if (!handle) return;
      state.directory = handle;
      elements.directoryLabel.textContent = `上次选择：${handle.name}（正在检查权限）`;
      const permission = await handle.queryPermission(permissionOptions());
      if (permission === "granted") {
        await scanDirectory();
      } else {
        elements.reauthorize.hidden = false;
        elements.newArticle.disabled = true;
        setStatus("浏览器需要重新授权。请点击「重新授权」，或重新选择文章目录。");
      }
    } catch (error) {
      showError(error);
      elements.directoryLabel.textContent = "上次的目录授权不可用，请重新选择。";
    }
  }

  elements.chooseDirectory.addEventListener("click", chooseDirectory);
  elements.reauthorize.addEventListener("click", reauthorize);
  elements.newArticle.addEventListener("click", async () => {
    if (await closeEditor()) openEditor(null);
  });
  elements.cancelEdit.addEventListener("click", () => closeEditor().catch(showError));
  elements.articleForm.addEventListener("submit", saveArticle);
  elements.articleType.addEventListener("change", toggleTypeFields);
  elements.articleTitle.addEventListener("input", () => {
    if (!state.editing || state.editing.new) {
      elements.articleFilename.value = core.slugFromTitle(elements.articleTitle.value, elements.articleDate.value, state.files);
    }
  });
  elements.articleFilename.addEventListener("input", () => {
    const record = state.editing && !state.editing.new ? state.editing : null;
    elements.renameWarning.hidden = !record || elements.articleFilename.value === record.name;
  });
  elements.previewBody.addEventListener("click", () => {
    elements.bodyPreview.textContent = elements.articleBody.value;
    elements.bodyPreview.hidden = false;
  });
  window.addEventListener("beforeunload", (event) => {
    if (hasUnsavedChanges()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  if (!("showDirectoryPicker" in window)) {
    setStatus("当前浏览器不能直接选择本地文件夹。请使用随附的「Start Read Manager.cmd」以本机安全来源打开工具。");
  }
  restoreDirectory();
})();
