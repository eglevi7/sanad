const CACHE_NAME = "sanad-v1";
const ASSETS = [
    "/",
    "/ui/index.html",
    "/ui/style.css",
    "/ui/mobile.css",
    "/ui/tablet.css",
    "/ui/script.js",
    "/ui/logo.png",
    "/ui/icon-192.png",
    "/ui/icon-512.png"
];

// تثبيت
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS).catch(() => {});
        })
    );
    self.skipWaiting();
});

// تفعيل
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            );
        })
    );
    self.clients.claim();
});

// Fetch
self.addEventListener("fetch", (event) => {
    // متخزّنش POST requests
    if (event.request.method !== "GET") return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request).then((response) => {
                // خزّن الردود الجديدة
                if (response && response.status === 200) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            }).catch(() => cached);
        })
    );
});
