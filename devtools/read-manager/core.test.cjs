"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./core.js");

const externalText = `---
title: "原有标题"
target: external
external_url: "https://example.com/a?x=1&y=2"
weight: 10
_build:
  render: never
custom:
  nested:
    keep: "保留：未知字段"
---
`;

class MemoryFileHandle {
  constructor(name, text = "") {
    this.name = name;
    this.kind = "file";
    this.textContent = text;
  }
  async getFile() {
    const text = this.textContent;
    return { text: async () => text };
  }
  async createWritable() {
    let next = "";
    return {
      write: async (text) => { next = text; },
      close: async () => { this.textContent = next; },
      abort: async () => {}
    };
  }
}

class MemoryDirectoryHandle {
  constructor(name = "articles", files = []) {
    this.name = name;
    this.kind = "directory";
    this.files = new Map(files.map(([fileName, text]) => [fileName, new MemoryFileHandle(fileName, text)]));
    this.directories = new Map();
    this.failWrites = false;
  }
  async *entries() {
    yield* this.files.entries();
    yield* this.directories.entries();
  }
  async getFileHandle(name, options = {}) {
    if (this.failWrites && options.create) throw new Error("permission denied");
    if (this.files.has(name)) return this.files.get(name);
    if (!options.create) {
      const error = new Error("not found");
      error.name = "NotFoundError";
      throw error;
    }
    const handle = new MemoryFileHandle(name);
    this.files.set(name, handle);
    return handle;
  }
  async getDirectoryHandle(name, options = {}) {
    if (!this.directories.has(name)) {
      if (!options.create) throw new Error("not found");
      this.directories.set(name, new MemoryDirectoryHandle(name));
    }
    return this.directories.get(name);
  }
  async removeEntry(name) {
    if (!this.files.delete(name)) throw new Error("file not found");
  }
}

test("parses external records while ignoring nested unknown YAML fields", () => {
  const parsed = core.parseFrontMatter(externalText);
  assert.equal(parsed.article.title, "原有标题");
  assert.equal(parsed.article.target, "external");
  assert.equal(parsed.article.externalUrl, "https://example.com/a?x=1&y=2");
  assert.equal(parsed.article.weight, 10);
});

test("parses quoted YAML values with inline comments and leaves URL fragments intact", () => {
  const parsed = core.parseFrontMatter(`---\ntitle: "标题：带冒号" # keep title\n target: ignored\ntarget: external # link\nexternal_url: https://example.com/path#section\nweight: 10 # order\n---\n`);
  assert.equal(parsed.article.title, "标题：带冒号");
  assert.equal(parsed.article.externalUrl, "https://example.com/path#section");
  assert.equal(parsed.article.weight, 10);
});

test("updates managed metadata and preserves nested fields and exact body", () => {
  const text = `${externalText}\n正文保持\n换行：不变\n`;
  const updated = core.updateFrontMatter(text, {
    title: '标题: "引号"',
    external_url: "https://example.org/new?x=中文&y=2",
    weight: 20
  });
  assert.match(updated, /title: "标题: \\"引号\\""/);
  assert.match(updated, /custom:\n  nested:\n    keep: "保留：未知字段"/);
  assert.match(updated, /render: never/);
  assert.match(updated, /^weight: 20$/m);
  assert.doesNotMatch(updated, /^weight: "20"$/m);
  assert.ok(updated.endsWith("\n正文保持\n换行：不变\n"));
  assert.equal(core.parseFrontMatter(updated).article.externalUrl, "https://example.org/new?x=中文&y=2");
});

test("creates local and external Markdown with compatible metadata", () => {
  const local = core.createDocument({
    title: "中文：演讲",
    target: "local",
    weight: 30,
    date: "2026-10-22",
    author: '作者 "甲"',
    source: "书名",
    sourceUrl: "https://example.org/source",
    body: "第一段\n\n## 小节\n\n> 引文\n\n- 项目\n"
  });
  const parsed = core.parseFrontMatter(local);
  assert.equal(parsed.article.title, "中文：演讲");
  assert.equal(parsed.article.author, '作者 "甲"');
  assert.equal(parsed.article.body, "\n第一段\n\n## 小节\n\n> 引文\n\n- 项目\n");
  assert.doesNotMatch(local, /render: never/);

  const external = core.createDocument({
    title: "外链",
    target: "external",
    externalUrl: "https://example.com/article",
    weight: 40
  });
  assert.match(external, /target: external/);
  assert.match(external, /_build:\n  render: never/);
});

test("replaces only local article body and keeps front matter", () => {
  const source = `---\r\ntitle: "正文"\r\ntarget: local\r\nweight: 10\r\nunknown: keep\r\n---\r\n旧正文\r\n`;
  const updated = core.replaceBody(source, "第一段\n\n## 标题\n");
  assert.match(updated, /unknown: keep/);
  assert.ok(updated.endsWith("第一段\r\n\r\n## 标题\r\n"));
});

test("validates URLs, titles, weights, dates, and safe filenames", () => {
  assert.throws(() => core.validateExternalUrl("javascript:alert(1)"), /http/);
  assert.throws(() => core.validateExternalUrl("not a URL"), /有效/);
  assert.throws(() => core.validateFilename("../bad.md"), /文件名/);
  assert.throws(() => core.validateFilename("_index.md"), /索引/);
  assert.throws(() => core.validateArticleForm({ target: "external", title: "", weight: 1 }), /标题/);
  assert.throws(() => core.validateArticleForm({ target: "local", title: "A", weight: 1, body: " " }), /正文/);
  assert.throws(() => core.validateArticleForm({ target: "external", title: "A", weight: -1, externalUrl: "https://e.com" }), /排序位置/);
  assert.throws(() => core.validateArticleForm({ target: "external", title: "A", weight: 1, externalUrl: "https://e.com", date: "2026-99-99" }), /日期/);
});

test("generates unique safe filenames and leaves _index outside article handling", () => {
  const used = new Set(["hello-world.md"]);
  assert.equal(core.slugFromTitle("Hello World", "2026-10-22", used), "hello-world-2.md");
  assert.match(core.slugFromTitle("中文标题", "2026-10-22", new Set()), /^article-20261022-[a-z0-9]+\.md$/);
  assert.throws(() => core.parseFrontMatter("---\ntitle: x\n---\n"), /target/);
});

test("scans existing article files, ignores _index.md, and warns without changing unknown files", async () => {
  const directory = new MemoryDirectoryHandle("articles", [
    ["_index.md", "---\ntitle: Articles\n---\n"],
    ["first.md", externalText],
    ["unknown.md", "not front matter"]
  ]);
  const result = await core.scanDirectory(directory);
  assert.equal(result.articles.length, 1);
  assert.equal(result.articles[0].name, "first.md");
  assert.deepEqual(result.warnings.map((item) => item.name), ["unknown.md"]);
  assert.equal(directory.files.get("unknown.md").textContent, "not front matter");
});

test("creates external and local files directly and rejects duplicates and failed writes", async () => {
  const directory = new MemoryDirectoryHandle("articles", [["_index.md", "---\ntitle: Articles\n---\n"]]);
  const existing = new Set(["_index.md"]);
  await core.createArticle(directory, "external.md", {
    title: "外链标题",
    target: "external",
    externalUrl: "https://example.com/a",
    weight: 10
  }, existing);
  const body = "全文第一段\n\n## 章节\n\n> 引用\n";
  await core.createArticle(directory, "local.md", {
    title: "站内标题",
    target: "local",
    weight: 20,
    body
  }, new Set([...existing, "external.md"]));
  assert.match(directory.files.get("external.md").textContent, /render: never/);
  assert.ok(core.parseFrontMatter(directory.files.get("local.md").textContent).article.body.includes(body));
  const reopened = await core.scanDirectory(directory);
  assert.deepEqual(reopened.articles.map((item) => item.name), ["external.md", "local.md"]);
  await assert.rejects(core.createArticle(directory, "local.md", {
    title: "重复",
    target: "local",
    weight: 30,
    body
  }, new Set(["local.md"])), /已存在/);
  await assert.rejects(core.createArticle(directory, "external.md", {
    title: "目录刚增加的冲突文件",
    target: "external",
    externalUrl: "https://example.org",
    weight: 30
  }, new Set()), /存在/);
  directory.failWrites = true;
  await assert.rejects(core.createArticle(directory, "blocked.md", {
    title: "无权限",
    target: "external",
    externalUrl: "https://example.com",
    weight: 30
  }, new Set()), /permission denied/);
  assert.equal(directory.files.has("_index.md"), true);
});

test("edits metadata without losing local body or unknown front matter", async () => {
  const original = `---\ntitle: "Local"\ntarget: local\nweight: 10\nauthor: "A"\nunknown:\n  nested: preserve\n---\n\n完整正文：保留\n\n## 标题\n`;
  const directory = new MemoryDirectoryHandle("articles", [["local.md", original], ["_index.md", "---\ntitle: A\n---\n"]]);
  const record = (await core.scanDirectory(directory)).articles[0];
  await core.editArticle(directory, record, "local.md", {
    title: "更新标题",
    target: "local",
    weight: "20",
    author: "B",
    source: "",
    sourceUrl: "",
    date: "",
    body: record.article.body.replace(/^\n/, "")
  }, new Set(["local.md", "_index.md"]), record.article.body.replace(/^\n/, ""));
  const updated = directory.files.get("local.md").textContent;
  assert.match(updated, /title: "更新标题"/);
  assert.match(updated, /author: "B"/);
  assert.match(updated, /unknown:\n  nested: preserve/);
  assert.ok(updated.endsWith("\n\n完整正文：保留\n\n## 标题\n"));
  assert.equal(directory.files.get("_index.md").textContent, "---\ntitle: A\n---\n");
});

test("edits external title and URL without changing its type or render guard", async () => {
  const directory = new MemoryDirectoryHandle("articles", [
    ["external.md", externalText],
    ["_index.md", "---\ntitle: A\n---\n"]
  ]);
  const record = (await core.scanDirectory(directory)).articles[0];
  await core.editArticle(directory, record, "external.md", {
    title: "更新外链",
    target: "external",
    externalUrl: "https://example.org/updated?source=中文",
    weight: "20",
    date: "",
    body: ""
  }, new Set(["external.md", "_index.md"]), "");
  const updated = directory.files.get("external.md").textContent;
  const parsed = core.parseFrontMatter(updated);
  assert.equal(parsed.article.title, "更新外链");
  assert.equal(parsed.article.externalUrl, "https://example.org/updated?source=%E4%B8%AD%E6%96%87");
  assert.equal(parsed.article.target, "external");
  assert.match(updated, /render: never/);
  assert.match(updated, /custom:\n  nested:\n    keep: "保留：未知字段"/);
});

test("renames only after explicit target selection and keeps a backup of the old path", async () => {
  const directory = new MemoryDirectoryHandle("articles", [
    ["old-title.md", externalText],
    ["_index.md", "---\ntitle: A\n---\n"]
  ]);
  const record = (await core.scanDirectory(directory)).articles[0];
  await core.editArticle(directory, record, "new-title.md", {
    title: record.article.title,
    target: "external",
    externalUrl: record.article.externalUrl,
    weight: "10",
    body: ""
  }, new Set(["old-title.md", "_index.md"]), "");
  assert.equal(directory.files.has("old-title.md"), false);
  assert.match(directory.files.get("new-title.md").textContent, /https:\/\/example\.com\/a/);
  const backup = directory.directories.get(".read-manager-backups");
  assert.equal([...backup.files.values()][0].textContent, externalText);
});

test("reorders by changing weights only and keeps bodies and custom fields", async () => {
  const first = `---\ntitle: First\ntarget: local\nweight: 10\ncustom: keep\n---\n\nFirst body\n`;
  const second = `---\ntitle: Second\ntarget: local\nweight: 20\n---\n\nSecond body\n`;
  const directory = new MemoryDirectoryHandle("articles", [
    ["_index.md", "---\ntitle: A\n---\n"],
    ["first.md", first],
    ["second.md", second]
  ]);
  const records = (await core.scanDirectory(directory)).articles;
  assert.equal(records[0].name, "first.md");
  await core.reorderArticles(records, 0, 1);
  const scanned = await core.scanDirectory(directory);
  assert.deepEqual(scanned.articles.map((record) => record.name), ["second.md", "first.md"]);
  assert.equal(scanned.articles[0].article.weight, 10);
  assert.equal(scanned.articles[1].article.weight, 20);
  assert.match(directory.files.get("first.md").textContent, /custom: keep/);
  assert.ok(directory.files.get("first.md").textContent.endsWith("\n\nFirst body\n"));
});

test("deletion backs up only the identified article and stale files cannot be removed", async () => {
  const directory = new MemoryDirectoryHandle("articles", [
    ["_index.md", "---\ntitle: A\n---\n"],
    ["external.md", externalText],
    ["keep.md", externalText.replace("原有标题", "保留")]
  ]);
  const record = (await core.scanDirectory(directory)).articles.find((item) => item.name === "external.md");
  directory.files.get("external.md").textContent += "\nexternal edit\n";
  await assert.rejects(core.deleteArticle(directory, record), /已变化/);
  assert.equal(directory.files.has("external.md"), true);
  directory.files.get("external.md").textContent = record.text;
  await core.deleteArticle(directory, record);
  assert.equal(directory.files.has("external.md"), false);
  assert.equal(directory.files.has("_index.md"), true);
  assert.equal(directory.files.has("keep.md"), true);
  const backups = directory.directories.get(".read-manager-backups");
  assert.equal([...backups.files.values()][0].textContent, record.text);
});
