self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("fetch", (event) => { if (event.request.method === "GET") event.respondWith(fetch(event.request).catch(() => caches.match(event.request))); });
