// static/sw.js

const CACHE_NAME = 'synzo-v1';
const ASSETS_TO_CACHE = [
    '/static/css/style.css',
    '/static/files/manifest.json',
    '/static/images/synzo-icon.png',
    '/static/images/favicon.ico'
];

// 1. Install Event: Cache core static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

// 2. Activate Event: Clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// 3. Fetch Event: Network First, Fallback to Cache
self.addEventListener('fetch', (event) => {
    // Ignore non-GET requests (like POSTing a file upload)
    if (event.request.method !== 'GET') {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // If successful response, clone it and store in cache
                if (response && response.status === 200 && response.type === 'basic') {
                    const responseToCache = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return response;
            })
            .catch(() => {
                // If network fails (offline), try to serve from cache
                return caches.match(event.request);
            })
    );
});