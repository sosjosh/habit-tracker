const CACHE = 'habitquest-v1';
const SHELL = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

// Cache shell on install
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

// Remove old caches on activate
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network-first for API routes, cache-first for static assets
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  const isApi = e.request.method !== 'GET' || !url.pathname.startsWith('/static/');

  if (isApi) {
    // Always hit the network for data; fall back to offline page if available
    e.respondWith(fetch(e.request).catch(() => caches.match('/')));
  } else {
    // Cache-first for static files
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      }))
    );
  }
});
