const REPO_PATH = "/repos/0-1byte/0-1byte.github.io";
const WORKFLOW_PATH = "/actions/workflows/sync-weread.yml";
const MAIN_BRANCH = "main";
const SESSION_SECONDS = 12 * 60 * 60;
const STATE_SECONDS = 10 * 60;
const MAX_REQUEST_BYTES = 4096;
const MAX_UPLOAD_REQUEST_BYTES = 96 * 1024;
const MAX_UPLOAD_RECORDS = 20000;
const MAX_UPLOAD_CHUNKS = 300;
const MAX_UPLOAD_DATASET_BYTES = 32 * 1024 * 1024;
const MAX_UPLOAD_AGE_SECONDS = 90 * 60;
const ALLOWED_STEPS = new Set([
  "Checkout main",
  "Verify required sync code is present",
  "Set up Python 3.12",
  "Install WeRead dependencies",
  "Set up Node.js",
  "Set up Hugo",
  "Run offline synchronizer tests",
  "Run offline tests and syntax checks",
  "Verify pinned Worker origin",
  "Verify official gateway connectivity",
  "Synchronize into runner temporary storage",
  "Validate private dataset",
  "Build and verify manual-only homepage",
  "Upload validated dataset to private D1 storage",
  "Send safe run summary to the console",
]);

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

function cookieValue(request, name) {
  const cookie = request.headers.get("Cookie") || "";
  const entry = cookie.split(";").map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));
  return entry ? entry.slice(name.length + 1) : "";
}

function base64url(bytes) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/")
    + "=".repeat((4 - value.length % 4) % 4);
  return Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
}

function randomToken(bytes = 32) {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

async function hmac(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"],
  );
  return base64url(new Uint8Array(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)),
  ));
}

function constantTimeEqual(left, right) {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) {
    diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return diff === 0;
}

function siteCookie(name, value, maxAge, sameSite = "Lax") {
  return `${name}=${value}; Path=/; Secure; HttpOnly; SameSite=${sameSite}; Max-Age=${maxAge}`;
}

function clearCookie(name, sameSite = "Lax") {
  return siteCookie(name, "", 0, sameSite);
}

function siteOrigin(env) {
  return new URL(env.SITE_ORIGIN).origin;
}

function workerOrigin(env) {
  const value = env.WORKER_ORIGIN;
  if (typeof value !== "string") throw new Error("invalid_worker_origin");
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password
    || url.port || url.pathname !== "/" || url.search || url.hash
    || !/^weread-sync-console\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.workers\.dev$/i.test(url.hostname)
    || url.origin !== value.replace(/\/$/, "")) {
    throw new Error("invalid_worker_origin");
  }
  return url.origin;
}

function hasValidWorkerOrigin(value) {
  try {
    workerOrigin({ WORKER_ORIGIN: value });
    return true;
  } catch (_) {
    return false;
  }
}

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin || origin !== siteOrigin(env)) return null;
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token, Idempotency-Key",
    "Access-Control-Max-Age": "600",
    Vary: "Origin",
  };
}

async function signedValue(value, secret) {
  return `${value}.${await hmac(value, secret)}`;
}

async function verifySignedValue(value, secret) {
  const index = value.lastIndexOf(".");
  if (index <= 0) return "";
  const payload = value.slice(0, index);
  const signature = value.slice(index + 1);
  const expected = await hmac(payload, secret);
  return constantTimeEqual(signature, expected) ? payload : "";
}

async function readSession(request, env) {
  const signed = cookieValue(request, "__Host-weread-session");
  const payload = await verifySignedValue(signed, env.SESSION_SECRET);
  if (!payload) return null;
  try {
    const session = JSON.parse(new TextDecoder().decode(fromBase64url(payload)));
    if (session.exp <= Date.now()
      || session.sub !== env.ADMIN_GITHUB_LOGIN
      || typeof session.csrf !== "string") return null;
    return session;
  } catch (_) {
    return null;
  }
}

async function github(requestPath, env, options = {}) {
  const response = await fetch(`https://api.github.com${requestPath}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "weread-sync-console",
      ...(options.headers || {}),
    },
  });
  return response;
}

function coordinator(env) {
  const id = env.SYNC_COORDINATOR.idFromName("only-admin-sync");
  return env.SYNC_COORDINATOR.get(id);
}

async function boundedBody(request, maxBytes = MAX_REQUEST_BYTES) {
  const declared = Number(request.headers.get("Content-Length") || 0);
  if (declared > maxBytes) return null;
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > maxBytes) return null;
  try {
    return JSON.parse(text);
  } catch (_) {
    return null;
  }
}

function exactKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

function validText(value, maxLength) {
  return typeof value === "string" && value.trim().length > 0
    && value.length <= maxLength
    && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value);
}

const PRIVATE_QUOTE_KEYS = [
  "text", "source_type", "source", "author", "chapter",
  "book_id", "chapter_uid", "bookmark_id", "also_sources",
];
const PRIVATE_SOURCE_KEYS = [
  "source", "author", "chapter", "book_id", "chapter_uid", "bookmark_id",
];

function validAttribution(source) {
  return exactKeys(source, PRIVATE_SOURCE_KEYS)
    && validText(source.source, 2000)
    && typeof source.author === "string" && source.author.length <= 2000
    && typeof source.chapter === "string" && source.chapter.length <= 2000
    && validText(source.book_id, 512)
    && typeof source.chapter_uid === "string" && source.chapter_uid.length <= 512
    && typeof source.bookmark_id === "string" && source.bookmark_id.length <= 512;
}

function validPrivateQuote(quote) {
  if (!exactKeys(quote, PRIVATE_QUOTE_KEYS)) return false;
  if (!validText(quote.text, 20000)
    || quote.source_type !== "weread"
    || !validText(quote.source, 2000)
    || quote.source.toLowerCase() === "weread"
    || typeof quote.author !== "string" || quote.author.length > 2000
    || typeof quote.chapter !== "string" || quote.chapter.length > 2000
    || !validText(quote.book_id, 512)
    || typeof quote.chapter_uid !== "string" || quote.chapter_uid.length > 512
    || typeof quote.bookmark_id !== "string" || quote.bookmark_id.length > 512
    || !Array.isArray(quote.also_sources) || quote.also_sources.length > 100
    || !quote.also_sources.every(validAttribution)) return false;
  const identities = new Set([JSON.stringify([
    quote.book_id, quote.chapter_uid, quote.bookmark_id,
  ])]);
  for (const source of quote.also_sources) {
    const identity = JSON.stringify([
      source.book_id, source.chapter_uid, source.bookmark_id,
    ]);
    if (identities.has(identity)) return false;
    identities.add(identity);
  }
  return true;
}

function bearerMatches(request, secret) {
  if (typeof secret !== "string" || !secret) return false;
  const authorization = request.headers.get("Authorization") || "";
  const prefix = "Bearer ";
  return authorization.startsWith(prefix)
    && constantTimeEqual(authorization.slice(prefix.length), secret);
}

function hasJsonContentType(request) {
  return (request.headers.get("Content-Type") || "")
    .toLowerCase().startsWith("application/json");
}

async function quoteDigest(text) {
  const bytes = new Uint8Array(await crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(text),
  ));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function accepted(body = {}) {
  return json({ accepted: true, ...body });
}

function publicCorsHeaders(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return {};
  if (origin !== siteOrigin(env)) return null;
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Accept",
    "Access-Control-Max-Age": "600",
    Vary: "Origin",
  };
}

async function publicQuote(request, env) {
  if (request.method === "OPTIONS") {
    const cors = publicCorsHeaders(request, env);
    return cors ? new Response(null, { status: 204, headers: cors })
      : json({ error: "origin_not_allowed" }, 403);
  }
  if (request.method !== "GET") return json({ error: "method_not_allowed" }, 405);
  const cors = publicCorsHeaders(request, env);
  if (!cors) return json({ error: "origin_not_allowed" }, 403);
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const rate = await env.PUBLIC_QUOTE_LIMITER.limit({ key: ip });
  if (!rate.success) {
    return json({ error: "rate_limited" }, 429, { ...cors, "Retry-After": "60" });
  }
  const row = await env.DB.prepare(
    "SELECT q.text, q.source, q.author, q.chapter FROM weread_quotes q "
      + "JOIN weread_active_dataset a ON a.singleton = 1 AND a.dataset_id = q.dataset_id "
      + "ORDER BY random() LIMIT 1",
  ).first();
  if (!row || !validText(row.text, 20000)) {
    return json({ error: "quote_unavailable" }, 503, cors);
  }
  return json({
    source_type: "weread",
    text: row.text,
    source: typeof row.source === "string" ? row.source : "",
    author: typeof row.author === "string" ? row.author : "",
    chapter: typeof row.chapter === "string" ? row.chapter : "",
  }, 200, cors);
}

async function uploadStart(request, env) {
  if (!bearerMatches(request, env.UPLOAD_SECRET)) return json({ error: "unauthorized" }, 401);
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!hasJsonContentType(request)) return json({ error: "invalid_content_type" }, 415);
  const body = await boundedBody(request);
  if (!body || !/^[0-9a-f-]{36}$/i.test(body.upload_id || "")
    || !Number.isSafeInteger(body.record_count)
    || body.record_count < 1 || body.record_count > MAX_UPLOAD_RECORDS
    || !Number.isSafeInteger(body.chunk_count)
    || body.chunk_count < 1 || body.chunk_count > MAX_UPLOAD_CHUNKS) {
    return json({ error: "invalid_upload_manifest" }, 400);
  }
  const existing = await env.DB.prepare(
    "SELECT expected_records, expected_chunks, state FROM weread_uploads WHERE upload_id = ?",
  ).bind(body.upload_id).first();
  if (existing) {
    if (existing.expected_records === body.record_count
      && existing.expected_chunks === body.chunk_count
      && ["receiving", "complete"].includes(existing.state)) return accepted();
    return json({ error: "upload_id_conflict" }, 409);
  }
  const cutoff = Math.floor(Date.now() / 1000) - MAX_UPLOAD_AGE_SECONDS;
  await env.DB.prepare(
    "UPDATE weread_uploads SET state = 'aborted' WHERE state = 'receiving' AND created_at <= ?",
  ).bind(cutoff).run();
  await env.DB.prepare(
    "DELETE FROM weread_upload_chunks WHERE upload_id IN "
      + "(SELECT upload_id FROM weread_uploads WHERE state = 'aborted' AND created_at <= ?)",
  ).bind(cutoff).run();
  const active = await env.DB.prepare(
    "SELECT upload_id FROM weread_uploads WHERE state = 'receiving' AND created_at > ? LIMIT 1",
  ).bind(cutoff).first();
  if (active) return json({ error: "upload_already_active" }, 409);
  await env.DB.prepare(
    "INSERT INTO weread_uploads (upload_id, expected_records, expected_chunks, state, created_at) "
      + "VALUES (?, ?, ?, 'receiving', ?)",
  ).bind(body.upload_id, body.record_count, body.chunk_count, Math.floor(Date.now() / 1000)).run();
  return accepted();
}

async function uploadChunk(request, env) {
  if (!bearerMatches(request, env.UPLOAD_SECRET)) return json({ error: "unauthorized" }, 401);
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!hasJsonContentType(request)) return json({ error: "invalid_content_type" }, 415);
  const body = await boundedBody(request, MAX_UPLOAD_REQUEST_BYTES);
  if (!body || !/^[0-9a-f-]{36}$/i.test(body.upload_id || "")
    || !Number.isSafeInteger(body.chunk_index) || !Array.isArray(body.records)
    || body.records.length < 1 || body.records.length > 200
    || !body.records.every(validPrivateQuote)) {
    return json({ error: "invalid_upload_chunk" }, 400);
  }
  const upload = await env.DB.prepare(
    "SELECT expected_chunks, state FROM weread_uploads WHERE upload_id = ?",
  ).bind(body.upload_id).first();
  if (!upload || upload.state !== "receiving"
    || body.chunk_index < 0 || body.chunk_index >= upload.expected_chunks) {
    return json({ error: "upload_not_receiving" }, 409);
  }
  const payload = JSON.stringify(body.records);
  const previous = await env.DB.prepare(
    "SELECT payload_json FROM weread_upload_chunks WHERE upload_id = ? AND chunk_index = ?",
  ).bind(body.upload_id, body.chunk_index).first();
  if (previous) {
    return previous.payload_json === payload ? accepted({ duplicate: true })
      : json({ error: "chunk_conflict" }, 409);
  }
  await env.DB.prepare(
    "INSERT INTO weread_upload_chunks (upload_id, chunk_index, payload_json, record_count) "
      + "SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM weread_uploads "
      + "WHERE upload_id = ? AND state = 'receiving')",
  ).bind(body.upload_id, body.chunk_index, payload, body.records.length, body.upload_id).run();
  const saved = await env.DB.prepare(
    "SELECT payload_json FROM weread_upload_chunks WHERE upload_id = ? AND chunk_index = ?",
  ).bind(body.upload_id, body.chunk_index).first();
  if (!saved || saved.payload_json !== payload) return json({ error: "chunk_conflict" }, 409);
  return accepted();
}

async function uploadComplete(request, env) {
  if (!bearerMatches(request, env.UPLOAD_SECRET)) return json({ error: "unauthorized" }, 401);
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!hasJsonContentType(request)) return json({ error: "invalid_content_type" }, 415);
  const body = await boundedBody(request);
  if (!body || !/^[0-9a-f-]{36}$/i.test(body.upload_id || "")) {
    return json({ error: "invalid_upload_id" }, 400);
  }
  const upload = await env.DB.prepare(
    "SELECT expected_records, expected_chunks, state FROM weread_uploads WHERE upload_id = ?",
  ).bind(body.upload_id).first();
  if (!upload) return json({ error: "upload_not_found" }, 404);
  if (upload.state === "complete") return accepted({ activated: true });
  if (upload.state !== "receiving") return json({ error: "upload_not_receiving" }, 409);
  const result = await env.DB.prepare(
    "SELECT chunk_index, payload_json, record_count FROM weread_upload_chunks "
      + "WHERE upload_id = ? ORDER BY chunk_index",
  ).bind(body.upload_id).all();
  const chunks = result.results || [];
  if (chunks.length !== upload.expected_chunks
    || chunks.some((chunk, index) => chunk.chunk_index !== index)) {
    return json({ error: "incomplete_upload" }, 409);
  }
  const records = [];
  const texts = new Set();
  let stagedBytes = 0;
  try {
    for (const chunk of chunks) {
      stagedBytes += new TextEncoder().encode(chunk.payload_json).byteLength;
      if (stagedBytes > MAX_UPLOAD_DATASET_BYTES) {
        return json({ error: "dataset_too_large" }, 413);
      }
      const batch = JSON.parse(chunk.payload_json);
      if (!Array.isArray(batch) || batch.length !== chunk.record_count
        || !batch.every(validPrivateQuote)) return json({ error: "invalid_staged_data" }, 400);
      for (const quote of batch) {
        if (texts.has(quote.text)) return json({ error: "duplicate_quote_text" }, 400);
        texts.add(quote.text);
        records.push(quote);
      }
    }
  } catch (_) {
    return json({ error: "invalid_staged_data" }, 400);
  }
  if (records.length !== upload.expected_records || records.length < 1
    || records.length > MAX_UPLOAD_RECORDS) {
    return json({ error: "record_count_mismatch" }, 400);
  }

  const db = env.DB;
  await db.prepare(
    "INSERT OR REPLACE INTO weread_datasets (dataset_id, record_count, activated_at) VALUES (?, ?, ?)",
  ).bind(body.upload_id, records.length, Math.floor(Date.now() / 1000)).run();
  await db.prepare("DELETE FROM weread_quotes WHERE dataset_id = ?")
    .bind(body.upload_id).run();
  for (let start = 0; start < records.length; start += 50) {
    const statements = [];
    for (const quote of records.slice(start, start + 50)) {
      statements.push(db.prepare(
        "INSERT INTO weread_quotes "
          + "(dataset_id, quote_key, text, source, author, chapter, private_json) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?)",
      ).bind(
        body.upload_id,
        await quoteDigest(quote.text),
        quote.text,
        quote.source,
        quote.author,
        quote.chapter,
        JSON.stringify(quote),
      ));
    }
    await db.batch(statements);
  }
  const stored = await db.prepare(
    "SELECT COUNT(*) AS count FROM weread_quotes WHERE dataset_id = ?",
  ).bind(body.upload_id).first();
  if (!stored || stored.count !== records.length) {
    return json({ error: "stored_record_count_mismatch" }, 500);
  }
  await db.batch([
    db.prepare(
      "INSERT INTO weread_active_dataset (singleton, dataset_id) VALUES (1, ?) "
        + "ON CONFLICT(singleton) DO UPDATE SET dataset_id = excluded.dataset_id",
    ).bind(body.upload_id),
    db.prepare("UPDATE weread_uploads SET state = 'complete' WHERE upload_id = ? AND state = 'receiving'")
      .bind(body.upload_id),
  ]);
  try {
    await db.prepare("DELETE FROM weread_quotes WHERE dataset_id != ?").bind(body.upload_id).run();
    await db.prepare("DELETE FROM weread_datasets WHERE dataset_id != ?").bind(body.upload_id).run();
    await db.prepare("DELETE FROM weread_upload_chunks WHERE upload_id = ?").bind(body.upload_id).run();
    await db.prepare("DELETE FROM weread_uploads WHERE upload_id != ?").bind(body.upload_id).run();
  } catch (error) {
    console.warn("Private dataset cleanup deferred:", error?.name || "Error");
  }
  return accepted({ activated: true, record_count: records.length });
}

async function uploadAbort(request, env) {
  if (!bearerMatches(request, env.UPLOAD_SECRET)) return json({ error: "unauthorized" }, 401);
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!hasJsonContentType(request)) return json({ error: "invalid_content_type" }, 415);
  const body = await boundedBody(request);
  if (!body || !/^[0-9a-f-]{36}$/i.test(body.upload_id || "")) {
    return json({ error: "invalid_upload_id" }, 400);
  }
  await env.DB.batch([
    env.DB.prepare("DELETE FROM weread_upload_chunks WHERE upload_id = ?").bind(body.upload_id),
    env.DB.prepare("UPDATE weread_uploads SET state = 'aborted' "
      + "WHERE upload_id = ? AND state = 'receiving'").bind(body.upload_id),
  ]);
  return accepted();
}

async function route(request, env) {
  const url = new URL(request.url);
  if (url.pathname.startsWith("/auth/") && url.origin !== workerOrigin(env)) {
    return new Response("Use the configured Worker origin.", { status: 421 });
  }
  if (url.pathname === "/public/quote") return publicQuote(request, env);
  if (url.pathname === "/internal/upload/start") return uploadStart(request, env);
  if (url.pathname === "/internal/upload/chunk") return uploadChunk(request, env);
  if (url.pathname === "/internal/upload/complete") return uploadComplete(request, env);
  if (url.pathname === "/internal/upload/abort") return uploadAbort(request, env);
  if (url.pathname === "/auth/login" && request.method === "GET") {
    const state = randomToken();
    const callback = new URL("/auth/callback", workerOrigin(env)).toString();
    const location = new URL("https://github.com/login/oauth/authorize");
    location.searchParams.set("client_id", env.GITHUB_OAUTH_CLIENT_ID);
    location.searchParams.set("redirect_uri", callback);
    location.searchParams.set("scope", "read:user");
    location.searchParams.set("state", state);
    const headers = new Headers({
      Location: location.toString(),
      "Cache-Control": "no-store",
    });
    headers.append("Set-Cookie",
      siteCookie("__Host-weread-oauth-state", state, STATE_SECONDS));
    return new Response(null, { status: 302, headers });
  }

  if (url.pathname === "/auth/callback" && request.method === "GET") {
    const state = url.searchParams.get("state") || "";
    const stateCookie = cookieValue(request, "__Host-weread-oauth-state");
    const code = url.searchParams.get("code") || "";
    if (!code || !state || !constantTimeEqual(state, stateCookie)) {
      return new Response("Authentication was not completed.", { status: 400 });
    }
    const callback = new URL("/auth/callback", workerOrigin(env)).toString();
    const tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: env.GITHUB_OAUTH_CLIENT_ID,
        client_secret: env.GITHUB_OAUTH_CLIENT_SECRET,
        code,
        redirect_uri: callback,
      }),
    });
    if (!tokenResponse.ok) return new Response("Authentication failed.", { status: 502 });
    const tokenBody = await tokenResponse.json();
    if (!tokenBody.access_token) return new Response("Authentication failed.", { status: 401 });
    const userResponse = await fetch("https://api.github.com/user", {
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${tokenBody.access_token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "weread-sync-console",
      },
    });
    if (!userResponse.ok) return new Response("Authentication failed.", { status: 502 });
    const user = await userResponse.json();
    if (user.login !== env.ADMIN_GITHUB_LOGIN) {
      return new Response("This account is not authorized.", { status: 403 });
    }
    const session = base64url(new TextEncoder().encode(JSON.stringify({
      sub: user.login,
      csrf: randomToken(),
      exp: Date.now() + SESSION_SECONDS * 1000,
    })));
    const headers = new Headers({
      Location: `${siteOrigin(env)}/admin/weread-sync/`,
      "Cache-Control": "no-store",
    });
    headers.append("Set-Cookie", siteCookie("__Host-weread-session",
      await signedValue(session, env.SESSION_SECRET), SESSION_SECONDS, "None"));
    headers.append("Set-Cookie", clearCookie("__Host-weread-oauth-state"));
    return new Response(null, { status: 302, headers });
  }

  if (url.pathname.startsWith("/api/")) {
    const cors = corsHeaders(request, env);
    if (!cors) return json({ error: "origin_not_allowed" }, 403);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    const session = await readSession(request, env);
    if (!session) return json({ error: "authentication_required" }, 401, cors);
    if (url.pathname === "/api/session" && request.method === "GET") {
      return json({ authenticated: true, login: session.sub, csrf: session.csrf }, 200, cors);
    }
    if (url.pathname === "/api/status" && request.method === "GET") {
      const response = await coordinator(env).fetch("https://coordinator/status");
      return new Response(response.body, {
        status: response.status,
        headers: { ...Object.fromEntries(response.headers), ...cors },
      });
    }
    if (url.pathname === "/api/trigger" && request.method === "POST") {
      if (!constantTimeEqual(request.headers.get("X-CSRF-Token") || "", session.csrf)) {
        return json({ error: "csrf_rejected" }, 403, cors);
      }
      if (!request.headers.get("Content-Type")?.startsWith("application/json")) {
        return json({ error: "invalid_content_type" }, 415, cors);
      }
      const body = await boundedBody(request);
      const idempotencyKey = request.headers.get("Idempotency-Key") || "";
      if (!body || Object.keys(body).length !== 0
        || !/^[0-9a-f-]{36}$/i.test(idempotencyKey)) {
        return json({ error: "invalid_request" }, 400, cors);
      }
      const response = await coordinator(env).fetch("https://coordinator/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: idempotencyKey, requested_by: session.sub }),
      });
      return new Response(response.body, {
        status: response.status,
        headers: { ...Object.fromEntries(response.headers), ...cors },
      });
    }
    if (url.pathname === "/api/logout" && request.method === "POST") {
      if (!constantTimeEqual(request.headers.get("X-CSRF-Token") || "", session.csrf)) {
        return json({ error: "csrf_rejected" }, 403, cors);
      }
      return json({ authenticated: false }, 200, {
        ...cors,
        "Set-Cookie": clearCookie("__Host-weread-session", "None"),
      });
    }
    return json({ error: "not_found" }, 404, cors);
  }

  if (url.pathname === "/internal/report" && request.method === "POST") {
    const authorization = request.headers.get("Authorization") || "";
    const expected = `Bearer ${env.WEREAD_SYNC_REPORT_SECRET}`;
    if (!env.REPORT_SECRET || !constantTimeEqual(authorization, expected)) {
      return json({ error: "unauthorized" }, 401);
    }
    const body = await boundedBody(request);
    if (!body || !/^\d+$/.test(String(body.run_id || ""))
      || !["success", "failure", "cancelled"].includes(body.job_status)) {
      return json({ error: "invalid_report" }, 400);
    }
    const stats = {};
    for (const key of [
      "notebooks", "eligible_books", "read_books", "highlights", "quotes",
      "missing_author", "missing_chapter", "unmapped_chapters",
      "ambiguous_chapter_ids",
    ]) {
      if (Number.isSafeInteger(body[key]) && body[key] >= 0) stats[key] = body[key];
    }
    const response = await coordinator(env).fetch("https://coordinator/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: body.run_id,
        run_attempt: Number.isSafeInteger(body.run_attempt) ? body.run_attempt : 1,
        job_status: body.job_status,
        stats,
      }),
    });
    return new Response(response.body, { status: response.status });
  }
  return new Response("Not found.", { status: 404 });
}

export default {
  async fetch(request, env) {
    try {
      const path = new URL(request.url).pathname;
      if (path === "/public/quote"
        && (!env.DB || !env.PUBLIC_QUOTE_LIMITER)) {
        return json({ error: "public_quote_service_unavailable" }, 503);
      }
      if (path.startsWith("/internal/upload/")
        && (!env.DB || !env.UPLOAD_SECRET)) {
        return json({ error: "upload_service_unavailable" }, 503);
      }
      if ((path.startsWith("/api/") || path.startsWith("/auth/"))
        && (!env.SESSION_SECRET || !env.GITHUB_TOKEN || !env.ADMIN_GITHUB_LOGIN
          || !hasValidWorkerOrigin(env.WORKER_ORIGIN))) {
        return new Response("Worker configuration is incomplete.", { status: 503 });
      }
      if (path.startsWith("/auth/")
        && (!env.GITHUB_OAUTH_CLIENT_ID || !env.GITHUB_OAUTH_CLIENT_SECRET)) {
        return new Response("Worker configuration is incomplete.", { status: 503 });
      }
      return await route(request, env);
    } catch (error) {
      console.error("WeRead sync console request failed:", error?.name || "Error");
      return json({ error: "internal_error" }, 500);
    }
  },
};

export class SyncCoordinator {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    return this.state.blockConcurrencyWhile(async () => {
      const path = new URL(request.url).pathname;
      if (path === "/trigger" && request.method === "POST") return this.trigger(request);
      if (path === "/status" && request.method === "GET") return this.status();
      if (path === "/report" && request.method === "POST") return this.report(request);
      return json({ error: "not_found" }, 404);
    });
  }

  async api(path, options = {}) {
    return github(`${REPO_PATH}${path}`, this.env, options);
  }

  async latestRun() {
    const response = await this.api(
      `${WORKFLOW_PATH}/runs?branch=${encodeURIComponent(MAIN_BRANCH)}&event=workflow_dispatch&per_page=5`,
    );
    if (!response.ok) throw new Error("GitHub Actions status request failed");
    const body = await response.json();
    const requestedAt = await this.state.storage.get("requested_at");
    const requestId = await this.state.storage.get("request_id");
    const runs = Array.isArray(body.workflow_runs) ? body.workflow_runs : [];
    return runs.find((run) => run.event === "workflow_dispatch"
      && run.head_branch === MAIN_BRANCH
      && run.display_title === `WeRead sync ${requestId}`
      && Number(run.created_at ? Date.parse(run.created_at) : 0)
        >= Number(requestedAt || 0) - 5_000) || null;
  }

  async trigger(request) {
    const body = await boundedBody(request);
    if (!body || body.requested_by !== this.env.ADMIN_GITHUB_LOGIN
      || !/^[0-9a-f-]{36}$/i.test(body.idempotency_key || "")) {
      return json({ error: "invalid_request" }, 400);
    }
    const previousKey = await this.state.storage.get("idempotency_key");
    if (previousKey === body.idempotency_key) {
      return json({ error: "duplicate_request" }, 409);
    }
    const active = await this.latestRun();
    if (active && ["queued", "in_progress", "waiting", "requested"].includes(active.status)) {
      return json({ error: "run_already_active" }, 409);
    }
    const lastDispatch = await this.state.storage.get("last_dispatch");
    const cooldown = Math.max(60, Number(this.env.TRIGGER_COOLDOWN_SECONDS) || 600);
    if (lastDispatch && Date.now() - lastDispatch < cooldown * 1000) {
      return json({ error: "rate_limited" }, 429, {
        "Retry-After": String(Math.ceil((cooldown * 1000 - (Date.now() - lastDispatch)) / 1000)),
      });
    }
    const owner = this.env.GITHUB_OWNER;
    const repo = this.env.GITHUB_REPO;
    const workflow = this.env.GITHUB_WORKFLOW;
    const branch = this.env.GITHUB_BRANCH;
    if (owner !== "0-1byte" || repo !== "0-1byte.github.io"
      || workflow !== "sync-weread.yml" || branch !== MAIN_BRANCH) {
      return json({ error: "fixed_target_configuration_invalid" }, 503);
    }
    const now = Date.now();
    const dispatchResponse = await this.api(
      `/actions/workflows/${WORKFLOW_PATH.split("/").pop()}/dispatches`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ref: MAIN_BRANCH,
          inputs: { mode: "sync", request_id: body.idempotency_key },
        }),
      },
    );
    if (dispatchResponse.status !== 204) {
      return json({ error: "github_dispatch_failed" }, 502);
    }
    await this.state.storage.put("requested_at", now);
    await this.state.storage.put("idempotency_key", body.idempotency_key);
    await this.state.storage.put("request_id", body.idempotency_key);
    await this.state.storage.put("requested_by", body.requested_by);
    await this.state.storage.put("last_dispatch", now);
    return json({ accepted: true, state: "queued", submitted_at: new Date(now).toISOString() }, 202);
  }

  async report(request) {
    const body = await boundedBody(request);
    if (!body || !/^\d+$/.test(String(body.run_id || ""))
      || !["success", "failure", "cancelled"].includes(body.job_status)
      || !body.stats || typeof body.stats !== "object") {
      return json({ error: "invalid_report" }, 400);
    }
    const run = await this.latestRun();
    if (!run || String(run.id) !== String(body.run_id)
      || (Number.isSafeInteger(run.run_attempt)
        && run.run_attempt !== body.run_attempt)) {
      return json({ error: "report_run_mismatch" }, 409);
    }
    if (body.job_status === "success") {
      const requiredStats = [
        "notebooks", "eligible_books", "read_books", "highlights", "quotes",
        "missing_author", "missing_chapter",
      ];
      if (!requiredStats.every((key) => Number.isSafeInteger(body.stats[key])
        && body.stats[key] >= 0)) {
        return json({ error: "incomplete_success_summary" }, 400);
      }
    }
    const report = {
      run_id: body.run_id,
      run_attempt: body.run_attempt,
      job_status: body.job_status,
      stats: body.stats,
      reported_at: new Date().toISOString(),
    };
    await this.state.storage.put("report", report);
    if (body.job_status === "success") {
      await this.state.storage.put("last_success", report);
    }
    return json({ accepted: true }, 202);
  }

  async status() {
    const lastDispatch = await this.state.storage.get("last_dispatch");
    const report = await this.state.storage.get("report");
    const lastSuccess = await this.state.storage.get("last_success");
    if (!lastDispatch) {
      return json({
        state: "idle",
        stats: lastSuccess ? lastSuccess.stats : null,
        last_success_at: lastSuccess ? lastSuccess.reported_at : "",
        current_stage: "",
        run_url: "",
      });
    }
    const run = await this.latestRun();
    if (!run) {
      if (Date.now() - lastDispatch > 5 * 60_000) {
        return json({ error: "workflow_run_not_visible" }, 503);
      }
      return json({
        state: "queued",
        stats: lastSuccess ? lastSuccess.stats : null,
        last_success_at: lastSuccess ? lastSuccess.reported_at : "",
        current_stage: "Waiting for GitHub Actions to start",
        submitted_at: new Date(lastDispatch).toISOString(),
        run_url: "",
      });
    }
    let state = "queued";
    if (run.status === "in_progress") state = "in_progress";
    if (run.status === "completed") {
      state = run.conclusion === "success" ? "success" : "failure";
    }
    let currentStage = state === "queued" ? "Queued in GitHub Actions"
      : state === "in_progress" ? "Workflow is running" : "";
    if (state === "in_progress") {
      const jobsResponse = await this.api(`/actions/runs/${run.id}/jobs?per_page=10`);
      if (jobsResponse.ok) {
        const jobsBody = await jobsResponse.json();
        const jobs = Array.isArray(jobsBody.jobs) ? jobsBody.jobs : [];
        const currentStep = jobs.flatMap((job) => job.steps || [])
          .find((step) => step.status === "in_progress");
        if (currentStep && ALLOWED_STEPS.has(currentStep.name)) {
          currentStage = currentStep.name;
        }
      }
    }
    const currentSuccess = report && String(report.run_id) === String(run.id)
      && report.run_attempt === run.run_attempt
      && report.job_status === "success" ? report : null;
    const summary = currentSuccess ? currentSuccess.stats
      : lastSuccess ? lastSuccess.stats : null;
    return json({
      state,
      current_stage: currentStage,
      submitted_at: run.created_at || new Date(lastDispatch).toISOString(),
      completed_at: run.completed_at || "",
      last_success_at: lastSuccess ? lastSuccess.reported_at : "",
      run_number: run.run_number || null,
      run_url: `https://github.com/0-1byte/0-1byte.github.io/actions/runs/${run.id}`,
      stats: summary,
    });
  }
}
