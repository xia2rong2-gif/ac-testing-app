const CACHE = 'ac-testing-v1';
const PRECACHE = [
  'index.html',
  'manifest.json',
  'app_data.json'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  // app_data.json: network-first (latest data), fall back to cache
  if (url.pathname.endsWith('/app_data.json')) {
    e.respondWith(
      fetch(e.request)
        .then(r => caches.open(CACHE).then(c => { c.put(e.request, r.clone()); return r; }))
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Everything else: cache-first
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(r => {
      caches.open(CACHE).then(c => c.put(e.request, r.clone()));
      return r;
    }))
  );
});
