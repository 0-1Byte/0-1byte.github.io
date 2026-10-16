"use strict";

const CACHE_NAME = "whereabouts-shell-v4";
const SHELL = [
  "/whereabouts/",
  "/whereabouts/index.html",
  "/whereabouts/styles.css",
  "/whereabouts/core.js",
  "/whereabouts/app.js",
  "/whereabouts/manifest.webmanifest",
  "/whereabouts/icon.svg",
  "/whereabouts/icon-192.png",
  "/whereabouts/icon-512.png",
  "/whereabouts/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("whereabouts-shell-") && key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;

  const url = new URL(request.url);
  if (SHELL.includes(url.pathname)) {
    const cacheKey = url.pathname === "/whereabouts/" ? "/whereabouts/" : request;
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          event.waitUntil(
            caches.open(CACHE_NAME)
              .then((cache) => cache.put(cacheKey, response.clone()))
              .catch((error) => console.error("无法更新离线应用外壳缓存：", error))
          );
        }
        return response;
      }).catch(async (error) => {
        const cache = await caches.open(CACHE_NAME);
        const cached = await cache.match(cacheKey);
        if (cached) return cached;
        throw error;
      })
    );
  }
});
