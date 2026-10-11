import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import worker, { SyncCoordinator } from "../src/index.js";

const sessionSecret = "test-only-session-secret";

function base64url(bytes) {
  return Buffer.from(bytes).toString("base64url");
}

async function signedSession(login = "admin", csrf = "csrf-test") {
  const payload = base64url(Buffer.from(JSON.stringify({
    sub: login,
    csrf,
    exp: Date.now() + 60_000,
  })));
  const key = await webcrypto.subtle.importKey(
    "raw", Buffer.from(sessionSecret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"],
  );
  const signature = base64url(new Uint8Array(
    await webcrypto.subtle.sign("HMAC", key, Buffer.from(payload)),
  ));
  return `__Host-weread-session=${payload}.${signature}`;
}

function env(overrides = {}) {
  return {
    SITE_ORIGIN: "https://0-1byte.github.io",
    WORKER_ORIGIN: "https://weread-sync-console.account.workers.dev",
    SESSION_SECRET: sessionSecret,
    GITHUB_TOKEN: "test-token",
    ADMIN_GITHUB_LOGIN: "admin",
    GITHUB_OWNER: "0-1byte",
    GITHUB_REPO: "0-1byte.github.io",
    GITHUB_WORKFLOW: "sync-weread.yml",
    GITHUB_BRANCH: "main",
    TRIGGER_COOLDOWN_SECONDS: "600",
    ...overrides,
  };
}

class MemoryDB {
  constructor() {
    this.uploads = new Map();
    this.chunks = new Map();
    this.datasets = new Map();
    this.quotes = new Map();
    this.active = "";
  }

  prepare(sql) {
    return new MemoryStatement(this, sql);
  }

  async batch(statements) {
    const results = [];
    for (const statement of statements) results.push(await statement.run());
    return results;
  }
}

class MemoryStatement {
  constructor(db, sql) {
    this.db = db;
    this.sql = sql.replace(/\s+/g, " ").trim();
    this.values = [];
  }

  bind(...values) {
    this.values = values;
    return this;
  }

  async first() {
    const { db, sql, values } = this;
    if (sql.startsWith("SELECT expected_records, expected_chunks, state FROM weread_uploads")) {
      const item = db.uploads.get(values[0]);
      return item ? { expected_records: item.expected_records, expected_chunks: item.expected_chunks, state: item.state } : null;
    }
    if (sql.startsWith("SELECT upload_id FROM weread_uploads")) {
      const item = Array.from(db.uploads.values()).find((upload) =>
        upload.state === "receiving" && upload.created_at > values[0]);
      return item ? { upload_id: item.upload_id } : null;
    }
    if (sql.startsWith("SELECT expected_chunks, state FROM weread_uploads")) {
      const item = db.uploads.get(values[0]);
      return item ? { expected_chunks: item.expected_chunks, state: item.state } : null;
    }
    if (sql.startsWith("SELECT payload_json FROM weread_upload_chunks")) {
      return db.chunks.get(`${values[0]}:${values[1]}`) || null;
    }
    if (sql.startsWith("SELECT COUNT(*) AS count FROM weread_quotes")) {
      return { count: Array.from(db.quotes.values()).filter((quote) => quote.dataset_id === values[0]).length };
    }
    if (sql.startsWith("SELECT q.text, q.source, q.author, q.chapter FROM weread_quotes")) {
      if (!db.active) return null;
      const row = Array.from(db.quotes.values()).find((quote) => quote.dataset_id === db.active);
      return row ? { text: row.text, source: row.source, author: row.author, chapter: row.chapter } : null;
    }
    throw new Error(`Unhandled fake D1 read: ${sql}`);
  }

  async all() {
    if (!this.sql.startsWith("SELECT chunk_index, payload_json, record_count FROM weread_upload_chunks")) {
      throw new Error(`Unhandled fake D1 query: ${this.sql}`);
    }
    return {
      results: Array.from(this.db.chunks.entries())
        .filter(([key]) => key.startsWith(`${this.values[0]}:`))
        .map(([, chunk]) => chunk)
        .sort((left, right) => left.chunk_index - right.chunk_index)
    };
  }

  async run() {
    const { db, sql, values } = this;
    if (sql.startsWith("UPDATE weread_uploads SET state = 'aborted' WHERE state = 'receiving'")) {
      for (const upload of db.uploads.values()) {
        if (upload.state === "receiving" && upload.created_at <= values[0]) upload.state = "aborted";
      }
    } else if (sql.startsWith("DELETE FROM weread_upload_chunks WHERE upload_id IN")) {
      for (const [key] of db.chunks) {
        const upload = db.uploads.get(key.split(":")[0]);
        if (upload && upload.state === "aborted" && upload.created_at <= values[0]) db.chunks.delete(key);
      }
    } else if (sql.startsWith("INSERT INTO weread_uploads")) {
      db.uploads.set(values[0], {
        upload_id: values[0],
        expected_records: values[1],
        expected_chunks: values[2],
        state: "receiving",
        created_at: values[3]
      });
    } else if (sql.startsWith("INSERT INTO weread_upload_chunks")) {
      const upload = db.uploads.get(values[4]);
      if (upload && upload.state === "receiving") {
        db.chunks.set(`${values[0]}:${values[1]}`, {
          upload_id: values[0],
          chunk_index: values[1],
          payload_json: values[2],
          record_count: values[3]
        });
      }
    } else if (sql.startsWith("INSERT OR REPLACE INTO weread_datasets")) {
      db.datasets.set(values[0], { record_count: values[1] });
    } else if (sql.startsWith("DELETE FROM weread_quotes WHERE dataset_id = ?")) {
      for (const [key, quote] of db.quotes) {
        if (quote.dataset_id === values[0]) db.quotes.delete(key);
      }
    } else if (sql.startsWith("INSERT INTO weread_quotes")) {
      const [dataset_id, quote_key, text, source, author, chapter, private_json] = values;
      db.quotes.set(`${dataset_id}:${quote_key}`, {
        dataset_id, quote_key, text, source, author, chapter, private_json
      });
    } else if (sql.startsWith("INSERT INTO weread_active_dataset")) {
      db.active = values[0];
    } else if (sql.startsWith("UPDATE weread_uploads SET state = 'complete'")) {
      const upload = db.uploads.get(values[0]);
      if (upload && upload.state === "receiving") upload.state = "complete";
    } else if (sql.startsWith("DELETE FROM weread_quotes WHERE dataset_id != ?")) {
      for (const [key, quote] of db.quotes) {
        if (quote.dataset_id !== values[0]) db.quotes.delete(key);
      }
    } else if (sql.startsWith("DELETE FROM weread_datasets WHERE dataset_id != ?")) {
      for (const key of db.datasets.keys()) if (key !== values[0]) db.datasets.delete(key);
    } else if (sql.startsWith("DELETE FROM weread_upload_chunks")) {
      for (const key of db.chunks.keys()) {
        if (sql.includes("upload_id != ?") ? !key.startsWith(`${values[0]}:`)
          : key.startsWith(`${values[0]}:`)) db.chunks.delete(key);
      }
    } else if (sql.startsWith("DELETE FROM weread_uploads")) {
      for (const key of db.uploads.keys()) {
        if (sql.includes("upload_id != ?") ? key !== values[0] : key === values[0]) {
          db.uploads.delete(key);
        }
      }
    } else if (sql.startsWith("UPDATE weread_uploads SET state = 'aborted'")) {
      const upload = db.uploads.get(values[0]);
      if (upload && upload.state === "receiving") upload.state = "aborted";
    } else {
      throw new Error(`Unhandled fake D1 write: ${sql}`);
    }
    return { success: true, meta: { changes: 1 } };
  }
}

function apiRequest(path, options = {}) {
  return new Request(`https://worker.example${path}`, {
    ...options,
    headers: {
      Origin: "https://0-1byte.github.io",
      ...(options.headers || {}),
    },
  });
}

test("OAuth uses the pinned workers.dev origin and rejects alternate hosts", async () => {
  const request = new Request(
    "https://weread-sync-console.account.workers.dev/auth/login",
  );
  const response = await worker.fetch(request, env({
    GITHUB_OAUTH_CLIENT_ID: "test-client-id",
    GITHUB_OAUTH_CLIENT_SECRET: "test-client-secret",
  }));
  assert.equal(response.status, 302);
  const authorization = new URL(response.headers.get("Location"));
  assert.equal(
    authorization.searchParams.get("redirect_uri"),
    "https://weread-sync-console.account.workers.dev/auth/callback",
  );

  const alias = await worker.fetch(new Request("https://attacker.workers.dev/auth/login"),
    env({
      GITHUB_OAUTH_CLIENT_ID: "test-client-id",
      GITHUB_OAUTH_CLIENT_SECRET: "test-client-secret",
    }));
  assert.equal(alias.status, 421);
});

const uploadSecret = "test-only-upload-secret";
const uploadId = "123e4567-e89b-12d3-a456-426614174000";
const privateQuote = (text, bookmarkId) => ({
  text,
  source_type: "weread",
  source: "合成测试书",
  author: "合成作者",
  chapter: "合成章节",
  book_id: "synthetic-book-id",
  chapter_uid: "synthetic-chapter-id",
  bookmark_id: bookmarkId,
  also_sources: []
});

function uploadRequest(path, body, options = {}) {
  return new Request(`https://worker.example${path}`, {
    method: options.method || "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.authorized ? { Authorization: `Bearer ${uploadSecret}` } : {}),
      ...(options.headers || {})
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

function privateEnv(db, overrides = {}) {
  return env({
    DB: db,
    UPLOAD_SECRET: uploadSecret,
    PUBLIC_QUOTE_LIMITER: { limit: async () => ({ success: true }) },
    ...overrides
  });
}

test("private upload rejects unauthenticated, empty and oversized manifests", async () => {
  const db = new MemoryDB();
  const service = privateEnv(db);
  const unauthorized = await worker.fetch(
    uploadRequest("/internal/upload/start", { upload_id: uploadId, record_count: 1, chunk_count: 1 }),
    service,
  );
  assert.equal(unauthorized.status, 401);
  const unconfiguredSecret = await worker.fetch(
    uploadRequest("/internal/upload/start", {
      upload_id: uploadId, record_count: 1, chunk_count: 1
    }, { authorized: true }),
    privateEnv(db, { UPLOAD_SECRET: "" }),
  );
  assert.equal(unconfiguredSecret.status, 503);
  const empty = await worker.fetch(
    uploadRequest("/internal/upload/start", { upload_id: uploadId, record_count: 0, chunk_count: 0 }, { authorized: true }),
    service,
  );
  assert.equal(empty.status, 400);
  const oversized = await worker.fetch(
    uploadRequest("/internal/upload/start", { upload_id: uploadId, record_count: 20001, chunk_count: 1 }, { authorized: true }),
    service,
  );
  assert.equal(oversized.status, 400);
  assert.equal(db.uploads.size, 0);
});

test("credential preflight routes authenticate before rejecting empty bodies without side effects", async () => {
  const db = new MemoryDB();
  let dbCalls = 0;
  const guardedDb = {
    prepare(sql) {
      dbCalls += 1;
      return db.prepare(sql);
    },
    batch(statements) {
      dbCalls += 1;
      return db.batch(statements);
    },
  };
  let coordinatorCalls = 0;
  const service = privateEnv(guardedDb, {
    REPORT_SECRET: "test-only-report-secret",
    SYNC_COORDINATOR: {
      idFromName: (name) => name,
      get: () => ({
        fetch: async () => {
          coordinatorCalls += 1;
          return Response.json({ accepted: true }, { status: 202 });
        },
      }),
    },
  });

  const upload = async (authorization) => worker.fetch(
    uploadRequest("/internal/upload/start", {}, {
      authorized: authorization === `******`,
      headers: authorization === `******` ? {} : { Authorization: authorization },
    }),
    service,
  );
  const report = async (authorization) => worker.fetch(new Request(
    "https://worker.example/internal/report",
    {
      method: "POST",
      headers: { Authorization: authorization, "Content-Type": "application/json" },
      body: "{}",
    },
  ), service);

  assert.equal((await upload(`******`)).status, 400);
  assert.equal(dbCalls, 0);
  assert.equal((await upload("Bearer incorrect")).status, 401);
  assert.equal(dbCalls, 0);

  assert.equal((await report("Bearer test-only-report-secret")).status, 400);
  assert.equal(coordinatorCalls, 0);
  assert.equal((await report("Bearer incorrect")).status, 401);
  assert.equal(coordinatorCalls, 0);
  assert.equal(db.uploads.size, 0);
});

test("invalid or incomplete upload leaves the active private dataset untouched", async () => {
  const db = new MemoryDB();
  db.active = "previous";
  db.datasets.set("previous", { record_count: 1 });
  db.quotes.set("previous:old", {
    dataset_id: "previous", text: "旧版本合成句", source: "旧书",
    author: "", chapter: "", private_json: "{}"
  });
  const service = privateEnv(db);
  const start = (recordCount, chunkCount) => worker.fetch(uploadRequest(
    "/internal/upload/start",
    { upload_id: uploadId, record_count: recordCount, chunk_count: chunkCount },
    { authorized: true },
  ), service);

  assert.equal((await start(2, 2)).status, 200);
  assert.equal((await start(2, 2)).status, 200);
  const invalid = await worker.fetch(uploadRequest("/internal/upload/chunk", {
    upload_id: uploadId,
    chunk_index: 0,
    records: [{ ...privateQuote("不合规", "bad"), source_type: "manual" }]
  }, { authorized: true }), service);
  assert.equal(invalid.status, 400);
  const duplicateAttribution = privateQuote("重复出处合成句", "same-mark");
  duplicateAttribution.also_sources = [{
    source: "另一本合成书",
    author: "合成作者",
    chapter: "合成章节",
    book_id: "synthetic-book-id",
    chapter_uid: "synthetic-chapter-id",
    bookmark_id: "same-mark"
  }];
  const invalidAttribution = await worker.fetch(uploadRequest("/internal/upload/chunk", {
    upload_id: uploadId, chunk_index: 0, records: [duplicateAttribution]
  }, { authorized: true }), service);
  assert.equal(invalidAttribution.status, 400);

  const firstChunk = {
    upload_id: uploadId, chunk_index: 0, records: [privateQuote("合成句甲", "mark-a")]
  };
  assert.equal((await worker.fetch(uploadRequest("/internal/upload/chunk", firstChunk, { authorized: true }), service)).status, 200);
  const duplicateChunk = await worker.fetch(uploadRequest("/internal/upload/chunk", firstChunk, { authorized: true }), service);
  assert.deepEqual(await duplicateChunk.json(), { accepted: true, duplicate: true });
  const incomplete = await worker.fetch(uploadRequest("/internal/upload/complete", { upload_id: uploadId }, { authorized: true }), service);
  assert.equal(incomplete.status, 409);
  assert.equal(db.active, "previous");
  assert.equal(db.quotes.has("previous:old"), true);
});

test("completed private upload atomically activates data and public API returns only one whitelisted quote", async () => {
  const db = new MemoryDB();
  db.active = "previous";
  db.datasets.set("previous", { record_count: 1 });
  db.quotes.set("previous:old", {
    dataset_id: "previous", text: "旧版本合成句", source: "旧书",
    author: "", chapter: "", private_json: "{}"
  });
  const service = privateEnv(db);
  const upload = async (path, body) => worker.fetch(
    uploadRequest(path, body, { authorized: true }), service,
  );
  assert.equal((await upload("/internal/upload/start", {
    upload_id: uploadId, record_count: 2, chunk_count: 2
  })).status, 200);
  for (const [index, text] of ["新合成句甲", "新合成句乙"].entries()) {
    assert.equal((await upload("/internal/upload/chunk", {
      upload_id: uploadId,
      chunk_index: index,
      records: [privateQuote(text, `mark-${index}`)]
    })).status, 200);
  }
  const completed = await upload("/internal/upload/complete", { upload_id: uploadId });
  assert.deepEqual(await completed.json(), {
    accepted: true, activated: true, record_count: 2
  });
  assert.equal(db.active, uploadId);
  assert.equal(db.quotes.size, 2);
  const retry = await upload("/internal/upload/complete", { upload_id: uploadId });
  assert.equal(retry.status, 200);

  const publicResponse = await worker.fetch(new Request("https://worker.example/public/quote", {
    headers: {
      Origin: "https://0-1byte.github.io",
      "CF-Connecting-IP": "192.0.2.10"
    }
  }), service);
  assert.equal(publicResponse.status, 200);
  assert.equal(publicResponse.headers.get("Cache-Control"), "no-store");
  assert.equal(
    publicResponse.headers.get("Access-Control-Allow-Origin"),
    "https://0-1byte.github.io"
  );
  const result = await publicResponse.json();
  assert.deepEqual(Object.keys(result).sort(), ["author", "chapter", "source", "source_type", "text"]);
  assert.equal(result.source_type, "weread");
  assert.ok(result.text.startsWith("新合成句"));
  assert.equal(JSON.stringify(result).includes("book_id"), false);
  assert.equal(JSON.stringify(result).includes("also_sources"), false);
});

test("public quote endpoint is read-only, rate limited, and rejects other origins", async () => {
  const db = new MemoryDB();
  const service = privateEnv(db, {
    PUBLIC_QUOTE_LIMITER: { limit: async () => ({ success: false }) }
  });

  test("public quote CORS preflight allows only the configured site origin", async () => {
    const service = privateEnv(new MemoryDB());
    const allowed = await worker.fetch(new Request("https://worker.example/public/quote", {
      method: "OPTIONS",
      headers: {
        Origin: "https://0-1byte.github.io",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "accept"
      }
    }), service);
    assert.equal(allowed.status, 204);
    assert.equal(allowed.headers.get("Access-Control-Allow-Origin"), "https://0-1byte.github.io");
    assert.equal(allowed.headers.get("Access-Control-Allow-Headers"), "Accept");

    const rejected = await worker.fetch(new Request("https://worker.example/public/quote", {
      method: "OPTIONS",
      headers: { Origin: "https://attacker.example" }
    }), service);
    assert.equal(rejected.status, 403);
  });
  const limited = await worker.fetch(new Request("https://worker.example/public/quote", {
    headers: { Origin: "https://0-1byte.github.io", "CF-Connecting-IP": "192.0.2.11" }
  }), service);
  assert.equal(limited.status, 429);
  const wrongOrigin = await worker.fetch(new Request("https://worker.example/public/quote", {
    headers: { Origin: "https://attacker.example" }
  }), service);
  assert.equal(wrongOrigin.status, 403);
  const writeMethod = await worker.fetch(new Request("https://worker.example/public/quote", {
    method: "POST",
    headers: { Origin: "https://0-1byte.github.io" }
  }), service);
  assert.equal(writeMethod.status, 405);
});

test("unauthenticated API access is rejected", async () => {
  const response = await worker.fetch(apiRequest("/api/session"), env());
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "authentication_required" });
});

test("requests from a different origin are rejected before session checks", async () => {
  const response = await worker.fetch(new Request("https://worker.example/api/session", {
    headers: { Origin: "https://attacker.example" },
  }), env());
  assert.equal(response.status, 403);
});

test("only the signed admin session is returned to the browser", async () => {
  const response = await worker.fetch(apiRequest("/api/session", {
    headers: { Cookie: await signedSession() },
  }), env());
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    authenticated: true,
    login: "admin",
    csrf: "csrf-test",
  });
});

test("trigger rejects a missing CSRF token without calling GitHub", async () => {
  const originalFetch = globalThis.fetch;
  let githubCalls = 0;
  globalThis.fetch = async () => {
    githubCalls += 1;
    throw new Error("unexpected request");
  };
  try {
    const response = await worker.fetch(apiRequest("/api/trigger", {
      method: "POST",
      headers: {
        Cookie: await signedSession(),
        "Content-Type": "application/json",
        "Idempotency-Key": "123e4567-e89b-12d3-a456-426614174000",
      },
      body: "{}",
    }), env());
    assert.equal(response.status, 403);
    assert.deepEqual(await response.json(), { error: "csrf_rejected" });
    assert.equal(githubCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a summary callback cannot attach counts to an unrelated workflow run", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    workflow_runs: [{
      id: 42,
      event: "workflow_dispatch",
      head_branch: "main",
      display_title: "Unrelated workflow",
      created_at: new Date().toISOString(),
      status: "completed",
    }],
  }), { status: 200 });
  const values = new Map([
    ["requested_at", Date.now()],
    ["request_id", "expected-id"],
  ]);
  const writes = [];
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => { writes.push(key); values.set(key, value); },
    },
  };
  try {
    const coordinator = new SyncCoordinator(state, env());
    const response = await coordinator.fetch(new Request("https://coordinator/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: "42",
        run_attempt: 1,
        job_status: "success",
        stats: { quotes: 123 },
      }),
    }));
    assert.equal(response.status, 409);
    assert.deepEqual(await response.json(), { error: "report_run_mismatch" });
    assert.equal(writes.length, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a matching completed run exposes only validated aggregate statistics", async () => {
  const originalFetch = globalThis.fetch;
  const run = {
    id: 43,
    event: "workflow_dispatch",
    head_branch: "main",
    display_title: "WeRead sync expected-id",
    created_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
    run_attempt: 1,
    run_number: 12,
    status: "completed",
    conclusion: "success",
  };
  globalThis.fetch = async () => new Response(JSON.stringify({
    workflow_runs: [run],
  }), { status: 200 });
  const values = new Map([
    ["requested_at", Date.now()],
    ["request_id", "expected-id"],
    ["last_dispatch", Date.now()],
  ]);
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
    },
  };
  const stats = {
    notebooks: 298,
    eligible_books: 286,
    read_books: 286,
    highlights: 5208,
    quotes: 5205,
    missing_author: 7,
    missing_chapter: 20,
  };
  try {
    const coordinator = new SyncCoordinator(state, env());
    const report = await coordinator.fetch(new Request("https://coordinator/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: "43",
        run_attempt: 1,
        job_status: "success",
        stats,
      }),
    }));
    assert.equal(report.status, 202);
    const status = await coordinator.fetch(new Request("https://coordinator/status"));
    const result = await status.json();
    assert.equal(result.state, "success");
    assert.deepEqual(result.stats, stats);
    assert.ok(result.last_success_at);
    assert.match(result.run_url, /^https:\/\/github\.com\/0-1byte\/0-1byte\.github\.io\/actions\/runs\/43$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("the coordinator rejects a configurable dispatch target", async () => {
  const originalFetch = globalThis.fetch;
  let dispatchCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/dispatches")) dispatchCalls += 1;
    return new Response(JSON.stringify({
      workflow_runs: [{
        id: 7,
        event: "workflow_dispatch",
        head_branch: "main",
        display_title: "WeRead sync previous-id",
        created_at: new Date().toISOString(),
        status: "completed",
      }],
    }), { status: 200 });
  };
  const values = new Map([
    ["requested_at", Date.now()],
    ["request_id", "previous-id"],
    ["idempotency_key", "previous-id"],
  ]);
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
      delete: async (key) => values.delete(key),
    },
  };
  try {
    const coordinator = new SyncCoordinator(state, env({ GITHUB_REPO: "other-repo" }));
    const response = await coordinator.fetch(new Request("https://coordinator/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "123e4567-e89b-12d3-a456-426614174000",
        requested_by: "admin",
      }),
    }));
    assert.equal(response.status, 503);
    assert.equal(dispatchCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("an existing queued run blocks a second trigger", async () => {
  const originalFetch = globalThis.fetch;
  let dispatchCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/dispatches")) {
      dispatchCalls += 1;
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify({
      workflow_runs: [{
        id: 8,
        event: "workflow_dispatch",
        head_branch: "main",
        display_title: "WeRead sync existing-id",
        created_at: new Date().toISOString(),
        status: "in_progress",
      }],
    }), { status: 200 });
  };
  const values = new Map([
    ["requested_at", Date.now()],
    ["request_id", "existing-id"],
    ["idempotency_key", "existing-id"],
    ["last_dispatch", Date.now() - 20 * 60_000],
  ]);
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
      delete: async (key) => values.delete(key),
    },
  };
  try {
    const coordinator = new SyncCoordinator(state, env());
    const response = await coordinator.fetch(new Request("https://coordinator/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "123e4567-e89b-12d3-a456-426614174000",
        requested_by: "admin",
      }),
    }));
    assert.equal(response.status, 409);
    assert.deepEqual(await response.json(), { error: "run_already_active" });
    assert.equal(dispatchCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a completed dispatch obeys the cooldown", async () => {
  const originalFetch = globalThis.fetch;
  let dispatchCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/dispatches")) {
      dispatchCalls += 1;
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify({
      workflow_runs: [{
        id: 9,
        event: "workflow_dispatch",
        head_branch: "main",
        display_title: "WeRead sync completed-id",
        created_at: new Date().toISOString(),
        status: "completed",
      }],
    }), { status: 200 });
  };
  const values = new Map([
    ["requested_at", Date.now()],
    ["request_id", "completed-id"],
    ["idempotency_key", "completed-id"],
    ["last_dispatch", Date.now()],
  ]);
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
      delete: async (key) => values.delete(key),
    },
  };
  try {
    const coordinator = new SyncCoordinator(state, env());
    const response = await coordinator.fetch(new Request("https://coordinator/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "123e4567-e89b-12d3-a456-426614174000",
        requested_by: "admin",
      }),
    }));
    assert.equal(response.status, 429);
    assert.deepEqual(await response.json(), { error: "rate_limited" });
    assert.equal(dispatchCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("workflow dispatch uses only the fixed main branch and workflow input", async () => {
  const originalFetch = globalThis.fetch;
  let dispatchPayload;
  globalThis.fetch = async (url, options = {}) => {
    if (String(url).endsWith("/dispatches")) {
      dispatchPayload = JSON.parse(options.body);
      return new Response(null, { status: 204 });
    }
    return new Response(JSON.stringify({ workflow_runs: [] }), { status: 200 });
  };
  const values = new Map();
  const state = {
    blockConcurrencyWhile: (callback) => callback(),
    storage: {
      get: async (key) => values.get(key),
      put: async (key, value) => values.set(key, value),
      delete: async (key) => values.delete(key),
    },
  };
  try {
    const coordinator = new SyncCoordinator(state, env());
    const response = await coordinator.fetch(new Request("https://coordinator/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: "123e4567-e89b-12d3-a456-426614174000",
        requested_by: "admin",
      }),
    }));
    assert.equal(response.status, 202);
    assert.equal(dispatchPayload.ref, "main");
    assert.deepEqual(dispatchPayload.inputs, {
      mode: "sync",
      request_id: "123e4567-e89b-12d3-a456-426614174000",
    });
    assert.equal(values.get("last_dispatch") > 0, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("internal report authenticates with REPORT_SECRET and rejects invalid credentials", async () => {
  let forwarded = 0;
  const service = env({
    REPORT_SECRET: "test-only-report-secret",
    SYNC_COORDINATOR: {
      idFromName: (name) => name,
      get: () => ({
        fetch: async () => {
          forwarded += 1;
          return Response.json({ accepted: true }, { status: 202 });
        },
      }),
    },
  });
  const body = JSON.stringify({
    run_id: "12345",
    run_attempt: 1,
    job_status: "success",
  });
  const request = (authorization) => new Request("https://worker.example/internal/report", {
    method: "POST",
    headers: { Authorization: authorization, "Content-Type": "application/json" },
    body,
  });

  const rejected = await worker.fetch(request("Bearer invalid-test-value"), service);
  assert.equal(rejected.status, 401);
  assert.equal(forwarded, 0);

  const accepted = await worker.fetch(request("Bearer test-only-report-secret"), service);
  assert.equal(accepted.status, 202);
  assert.equal(forwarded, 1);
});
