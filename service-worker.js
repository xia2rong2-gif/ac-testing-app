const CACHE = 'ac-testing-v2';
const PRECACHE = ['index.html', 'manifest.json'];
const DATA_URL = 'app_data.json';

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
  if (url.origin !== location.origin) return;

  // Normalize the URL: strip cache-busting query param for app_data.json
  let normalized = e.request;
  if (url.pathname.endsWith('/' + DATA_URL)) {
    normalized = new Request(DATA_URL, {headers: e.request.headers});
  }

  // app_data.json: network-first, fall back to cache, update cache on success
  if (url.pathname.endsWith('/' + DATA_URL)) {
    e.respondWith(
      fetch(normalized).then(r => {
        caches.open(CACHE).then(c => c.put(normalized, r.clone()));
        return r;
      }).catch(() => caches.match(normalized))
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
