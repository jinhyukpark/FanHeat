const CACHE = 'fanheat-shell-v4'
const SHELL = ['/', '/site.webmanifest', '/images/fanheat-app-icon-192.png?v=3', '/images/fanheat-app-icon-512.png?v=3', '/images/apple-touch-icon.png?v=3']

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) return
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(response => {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put('/', copy))
      return response
    }).catch(() => caches.match('/')))
    return
  }
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
    if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()))
    return response
  })))
})
