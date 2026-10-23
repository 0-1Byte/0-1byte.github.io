(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ReadManagerCore = api;
})(typeof globalThis === "undefined" ? this : globalThis, function () {
  "use strict";

  const MANAGED_FIELDS = new Set([
    "title",
    "target",
    "external_url",
    "date",
    "weight",
    "author",
    "source",
    "source_url"
  ]);

  function splitDocument(text) {
    const match = /^(\uFEFF?---)(\r\n|\n|\r)([\s\S]*?)(\r\n|\n|\r)---(\r\n|\n|\r|$)/.exec(text);
    if (!match) throw new Error("文件缺少有效的 YAML Front Matter，未作修改。");
    return {
      marker: match[1],
      newline: match[2],
      frontMatter: match[3],
      closingNewline: match[5],
      body: text.slice(match[0].length)
    };
  }

  function stripComment(value) {
    let quote = "";
    let escaped = false;
    for (let index = 0; index < value.length; index += 1) {
      const character = value[index];
      if (quote === '"') {
        if (escaped) escaped = false;
        else if (character === "\\") escaped = true;
        else if (character === '"') quote = "";
      } else if (quote === "'") {
        if (character === "'" && value[index + 1] === "'") index += 1;
        else if (character === "'") quote = "";
      } else if (character === '"' || character === "'") {
        quote = character;
      } else if (character === "#" && (index === 0 || /\s/.test(value[index - 1]))) {
        return value.slice(0, index).trimEnd();
      }
    }
    return value.trimEnd();
  }

  function unquote(value) {
    const trimmed = stripComment(value).trim();
    if (trimmed.startsWith('"')) {
      try {
        return JSON.parse(trimmed);
      } catch {
        throw new Error(`无法解析双引号 YAML 字符串：${trimmed}`);
      }
    }
    if (trimmed.startsWith("'")) {
      if (!trimmed.endsWith("'")) throw new Error(`无法解析单引号 YAML 字符串：${trimmed}`);
      return trimmed.slice(1, -1).replace(/''/g, "'");
    }
    return trimmed.replace(/\s+#.*$/, "").trim();
  }

  function parseFrontMatter(text) {
    const document = splitDocument(text);
    const fields = Object.create(null);
    for (const line of document.frontMatter.split(/\r\n|\n|\r/)) {
      const match = /^([A-Za-z_][\w-]*):(?:[ \t]*(.*))?$/.exec(line);
      if (!match) continue;
      const key = match[1];
      if (Object.hasOwn(fields, key)) throw new Error(`Front Matter 中存在重复字段：${key}`);
      fields[key] = unquote(match[2] || "");
    }
    for (const key of ["title", "target", "external_url", "date", "weight", "author", "source", "source_url"]) {
      if (/^(?:\||>)[+-]?$/.test(fields[key] || "")) {
        throw new Error(`字段 ${key} 使用不支持的多行 YAML 标量，文件未作修改。`);
      }
    }
    const target = fields.target;
    if (target !== "external" && target !== "local") {
      throw new Error('target 必须是 "external" 或 "local"。');
    }
    if (!fields.title) throw new Error("缺少文章标题。");
    if (target === "external" && !fields.external_url) throw new Error("外部文章缺少 external_url。");
    const weight = fields.weight === undefined || fields.weight === "" ? 0 : Number(fields.weight);
    if (!Number.isFinite(weight)) throw new Error("weight 不是有效数字。");
    return {
      ...document,
      fields,
      article: {
        title: fields.title,
        target,
        externalUrl: fields.external_url || "",
        date: fields.date || "",
        weight,
        author: fields.author || "",
        source: fields.source || "",
        sourceUrl: fields.source_url || "",
        body: document.body
      }
    };
  }

  function encodeScalar(value) {
    return JSON.stringify(String(value));
  }

  function formatManagedValue(key, value) {
    if (key === "weight") return String(value);
    if (key === "date" && /^\d{4}-\d{2}-\d{2}$/.test(String(value))) return String(value);
    return encodeScalar(value);
  }

  function updateFrontMatter(text, updates) {
    for (const key of Object.keys(updates)) {
      if (!MANAGED_FIELDS.has(key)) throw new Error(`不允许通过表单修改字段：${key}`);
    }
    const document = splitDocument(text);
    const lines = document.frontMatter.split(/\r\n|\n|\r/);
    for (const [key, value] of Object.entries(updates)) {
      const matches = [];
      for (let index = 0; index < lines.length; index += 1) {
        const match = new RegExp(`^${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:`).exec(lines[index]);
        if (match) matches.push(index);
      }
      if (matches.length > 1) throw new Error(`Front Matter 中存在重复字段：${key}`);
      if (value === undefined || value === null || value === "") {
        if (matches.length) lines.splice(matches[0], 1);
      } else if (matches.length) {
        lines[matches[0]] = `${key}: ${formatManagedValue(key, value)}`;
      } else {
        lines.push(`${key}: ${formatManagedValue(key, value)}`);
      }
    }
    const frontMatter = lines.join(document.newline);
    return `${document.marker}${document.newline}${frontMatter}${document.newline}---${document.closingNewline}${document.body}`;
  }

  function replaceBody(text, body) {
    const document = splitDocument(text);
    const normalized = String(body).replace(/\r\n?/g, "\n");
    const compatible = document.newline === "\n" ? normalized : normalized.replace(/\n/g, document.newline);
    return `${document.marker}${document.newline}${document.frontMatter}${document.newline}---${document.closingNewline}${compatible}`;
  }

  function validateExternalUrl(value) {
    let url;
    try {
      url = new URL(value);
    } catch {
      throw new Error("请输入有效的完整原文 URL。");
    }
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      throw new Error("原文 URL 必须以 http:// 或 https:// 开头。");
    }
    return url.href;
  }

  function validateFilename(value) {
    if (value === "_index.md") throw new Error("_index.md 是页面索引文件，不能作为文章。");
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*\.md$/.test(value)) {
      throw new Error("文件名只能使用小写英文字母、数字、连字符，并以 .md 结尾。");
    }
    return value;
  }

  function slugFromTitle(title, date, existingNames) {
    const ascii = title.normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    const fallback = `article-${(date || new Date().toISOString().slice(0, 10)).replace(/-/g, "")}-${Math.random().toString(36).slice(2, 7)}`;
    const stem = (ascii || fallback).slice(0, 70).replace(/-+$/g, "") || fallback;
    let candidate = `${stem}.md`;
    let suffix = 2;
    while (existingNames.has(candidate.toLowerCase())) {
      candidate = `${stem}-${suffix}.md`;
      suffix += 1;
    }
    return candidate;
  }

  function validateArticleForm(form) {
    const title = String(form.title || "").trim();
    if (!title) throw new Error("请填写文章标题。");
    const target = form.target;
    if (target !== "external" && target !== "local") throw new Error("请选择文章类型。");
    const weight = Number(form.weight);
    if (!Number.isInteger(weight) || weight < 0) throw new Error("排序位置必须是大于或等于 0 的整数。");
    let date = String(form.date || "").trim();
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error("日期请使用 YYYY-MM-DD 格式。");
    if (date) {
      const dateValue = new Date(`${date}T00:00:00Z`);
      if (Number.isNaN(dateValue.getTime()) || dateValue.toISOString().slice(0, 10) !== date) {
        throw new Error("日期无效。");
      }
    }
    const normalized = {
      title,
      target,
      weight,
      date,
      author: String(form.author || "").trim(),
      source: String(form.source || "").trim(),
      source_url: String(form.sourceUrl || "").trim(),
      external_url: ""
    };
    if (target === "external") normalized.external_url = validateExternalUrl(String(form.externalUrl || "").trim());
    if (target === "local" && !String(form.body || "").trim()) throw new Error("请填写站内文章正文。");
    if (normalized.source_url) normalized.source_url = validateExternalUrl(normalized.source_url);
    return normalized;
  }

  function createDocument(form) {
    const article = validateArticleForm(form);
    const lines = [
      "---",
      `title: ${encodeScalar(article.title)}`,
      `target: ${article.target}`
    ];
    if (article.target === "external") {
      lines.push(`external_url: ${encodeScalar(article.external_url)}`);
    }
    if (article.date) lines.push(`date: ${article.date}`);
    lines.push(`weight: ${article.weight}`);
    if (article.target === "external") {
      lines.push("_build:", "  render: never");
    } else {
      if (article.author) lines.push(`author: ${encodeScalar(article.author)}`);
      if (article.source) lines.push(`source: ${encodeScalar(article.source)}`);
      if (article.source_url) lines.push(`source_url: ${encodeScalar(article.source_url)}`);
    }
    lines.push("---", "");
    if (article.target === "local") lines.push(String(form.body).replace(/\r\n?/g, "\n"));
    return lines.join("\n");
  }

  async function scanDirectory(directory) {
    const articles = [];
    const warnings = [];
    const files = new Set();
    for await (const [name, handle] of directory.entries()) {
      files.add(name.toLowerCase());
      if (handle.kind !== "file" || !/\.md$/i.test(name) || name.toLowerCase() === "_index.md") continue;
      const file = await handle.getFile();
      const text = await file.text();
      try {
        const parsed = parseFrontMatter(text);
        articles.push({ handle, name, text, fields: parsed.fields, article: parsed.article });
      } catch (error) {
        warnings.push({ name, warning: error.message });
      }
    }
    articles.sort((a, b) => a.article.weight - b.article.weight || a.name.localeCompare(b.name));
    return { articles, warnings, files };
  }

  async function writeText(handle, text) {
    const writable = await handle.createWritable();
    try {
      await writable.write(text);
      await writable.close();
    } catch (error) {
      await writable.abort().catch(() => {});
      throw error;
    }
  }

  async function createArticle(directory, name, form, existingNames) {
    validateFilename(name);
    if (existingNames.has(name.toLowerCase())) throw new Error("该文件名已存在，请换一个名称。");
    try {
      await directory.getFileHandle(name);
      throw new Error("该文件名已经存在，请换一个名称。");
    } catch (error) {
      if (error.name !== "NotFoundError") throw error;
    }
    const text = createDocument(form);
    const handle = await directory.getFileHandle(name, { create: true });
    try {
      await writeText(handle, text);
    } catch (error) {
      try {
        await directory.removeEntry(name);
      } catch (cleanupError) {
        throw new Error(`写入失败，且无法清理未完成的新文件 ${name}：${cleanupError.message}`);
      }
      throw error;
    }
    return text;
  }

  async function backupAndRemove(directory, record, text) {
    const backupDirectory = await directory.getDirectoryHandle(".read-manager-backups", { create: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const suffix = Math.random().toString(36).slice(2, 8);
    const backup = await backupDirectory.getFileHandle(`${record.name}.${stamp}-${suffix}.bak`, { create: true });
    await writeText(backup, text);
    await directory.removeEntry(record.name);
  }

  async function editArticle(directory, record, name, form, existingNames, initialBody) {
    validateFilename(name);
    const currentFile = await record.handle.getFile();
    const current = await currentFile.text();
    if (current !== record.text) throw new Error("磁盘文件在打开表单后发生变化，请重新打开文章后再编辑。");
    const validated = validateArticleForm(form);
    if (validated.target !== record.article.target) {
      throw new Error("编辑时不能更改文章类型。请保留原类型，避免丢失文章内容或 URL。");
    }
    const updates = {
      title: validated.title,
      target: validated.target,
      weight: validated.weight
    };
    if (validated.target === "external") {
      updates.external_url = validated.external_url;
    } else {
      updates.date = validated.date || null;
      updates.author = validated.author || null;
      updates.source = validated.source || null;
      updates.source_url = validated.source_url || null;
    }
    let text = updateFrontMatter(current, updates);
    if (validated.target === "local" && form.body !== initialBody) text = replaceBody(text, form.body);

    const renaming = name !== record.name;
    if (renaming && existingNames.has(name.toLowerCase())) throw new Error("目标文件名已存在，请换一个名称。");
    if (renaming) {
      try {
        await directory.getFileHandle(name);
        throw new Error("目标文件名已经存在，请换一个名称。");
      } catch (error) {
        if (error.name !== "NotFoundError") throw error;
      }
      const next = await directory.getFileHandle(name, { create: true });
      try {
        await writeText(next, text);
      } catch (error) {
        try {
          await directory.removeEntry(name);
        } catch (cleanupError) {
          throw new Error(`改名写入失败，且无法清理未完成的新文件 ${name}：${cleanupError.message}`);
        }
        throw error;
      }
      try {
        await backupAndRemove(directory, record, current);
      } catch (error) {
        throw new Error(`新文件已写入，但旧文件尚未删除。请检查 ${record.name} 和 ${name}：${error.message}`);
      }
    } else {
      await writeText(record.handle, text);
    }
    return text;
  }

  async function deleteArticle(directory, record) {
    const currentFile = await record.handle.getFile();
    const current = await currentFile.text();
    if (current !== record.text) throw new Error("磁盘文件已变化，删除已取消。请重新扫描并确认后再操作。");
    await backupAndRemove(directory, record, current);
  }

  async function reorderArticles(records, index, direction) {
    const targetIndex = index + direction;
    if (!Number.isInteger(index) || targetIndex < 0 || targetIndex >= records.length) return false;
    const reordered = [...records];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    const originals = [];
    try {
      for (let position = 0; position < reordered.length; position += 1) {
        const record = reordered[position];
        const file = await record.handle.getFile();
        const current = await file.text();
        if (current !== record.text) throw new Error(`${record.name} 在排序时发生变化，未继续写入。请重新扫描。`);
        const next = updateFrontMatter(current, { weight: (position + 1) * 10 });
        if (next !== current) {
          originals.push({ record, text: current });
          await writeText(record.handle, next);
        }
      }
    } catch (error) {
      for (const item of originals.reverse()) await writeText(item.record.handle, item.text);
      throw error;
    }
    return true;
  }

  return {
    backupAndRemove,
    createDocument,
    createArticle,
    deleteArticle,
    editArticle,
    parseFrontMatter,
    replaceBody,
    reorderArticles,
    scanDirectory,
    slugFromTitle,
    updateFrontMatter,
    validateArticleForm,
    validateExternalUrl,
    validateFilename,
    writeText
  };
});
