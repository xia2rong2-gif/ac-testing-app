const CACHE = 'ac-testing-v10';

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(['index.html', 'manifest.json', 'app_data.json'])).then(() => self.skipWaiting())
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
  // Never intercept API requests (need real-time network)
  if (e.request.url.includes('/api/')) return;

  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;

  // Navigation: serve cached index.html when offline
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match('index.html'))
    );
    return;
  }

  // app_data.json: cache-first (ignore ?t= cache-busting param)
  if (e.request.url.includes('app_data.json')) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(r => {
          caches.open(CACHE).then(c => c.put(e.request, r.clone()));
          return r;
        });
      })
    );
    return;
  }

  // Other same-origin assets: network-first, fallback to cache
  e.respondWith(
    fetch(e.request).then(r => {
      caches.open(CACHE).then(c => c.put(e.request, r.clone()));
      return r;
    }).catch(() => caches.match(e.request))
  );
});
