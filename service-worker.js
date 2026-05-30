// Self-destruct: delete all caches and unregister this service worker
// The app no longer uses service workers to avoid caching old versions
self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
  // Unregister self
  self.registration.unregister();
});

// Do not intercept any fetch requests
self.addEventListener('fetch', e => {
  // pass through - no interception
});
