// Service Worker for Investment Dashboard PWA
// HTML/JSON は network-first (常に最新)、icon等は cache-first
const CACHE_NAME = "investment-dashboard-v3-snapshot";
const CORE_ASSETS = [
  "./manifest.webmanifest",
  "./icon-192.svg",
  "./icon-512.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(CORE_ASSETS).catch((err) => {
        console.warn("[SW] Partial cache failure (non-fatal):", err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;
  if (event.request.method !== "GET") return;

  // index.html / snapshot.json / data/* は常に最新を network から取得
  const path = url.pathname;
  const isFresh = path === "/" || path.endsWith(".html") || path.endsWith(".json") || path.includes("/data/");

  if (isFresh) {
    event.respondWith(
      fetch(event.request).then(fresh => {
        if (fresh && fresh.ok) {
          const copy = fresh.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
        }
        return fresh;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // それ以外 (icon, manifest等) は cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        fetch(event.request).then(fresh => {
          if (fresh && fresh.ok) {
            caches.open(CACHE_NAME).then(c => c.put(event.request, fresh.clone()));
          }
        }).catch(() => {});
        return cached;
      }
      return fetch(event.request).then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, copy));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
