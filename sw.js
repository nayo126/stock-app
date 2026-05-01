// Service Worker for Investment Dashboard PWA
// Provides offline support by caching core assets
const CACHE_NAME = "investment-dashboard-v1";
const CORE_ASSETS = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icon-192.svg",
  "./icon-512.svg"
];

// Install: cache core assets
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

// Activate: cleanup old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: cache-first for same-origin, network for others (external like TradingView)
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Only cache same-origin requests (local files)
  if (url.origin !== location.origin) {
    return; // Let browser handle external requests normally
  }
  // Skip non-GET
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        // Update in background
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
