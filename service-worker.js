const CACHE = 'ac-testing-v6';

self.addEventListener('install', e => {
  e.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Never intercept data requests — page handles caching via localStorage
  if (e.request.url.includes('/app_data.json')) return;

  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;

  // Network-first for everything: always try network, fall back to cache
  e.respondWith(
    fetch(e.request).then(r => {
      caches.open(CACHE).then(c => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request))
  );
});
