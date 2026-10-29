/**
 * ByaHero PWA Service Worker
 * Caches core assets for offline use and queues arrival logs for later sync.
 */
const CACHE_NAME = 'byahero-v1';
const OFFLINE_QUEUE = 'byahero-offline-queue';

const CORE_ASSETS = [
  '/',
  '/trip-planner',
  '/add-arrival',
  '/manage-locations',
  '/historical-data',
  '/static/css/pixelated.css',
  '/static/js/script.js',
  '/static/js/custom-select.js',
  '/static/js/konduktor.js',
  '/static/js/pwa.js',
  '/static/img/logo.png',
  '/static/img/favicon.png',
  '/static/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Handle offline arrival-queue POSTs.
  if (request.method === 'POST' && request.url.includes('/api/add-arrival-record')) {
    event.respondWith(handleOfflinePost(request));
    return;
  }

  // API and navigation requests: network first, fall back to cache.
  if (request.mode === 'navigate' || request.url.includes('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((res) => res || caches.match('/')))
    );
    return;
  }

  // Static assets: cache first.
  event.respondWith(
    caches.match(request).then((res) => {
      if (res) return res;
      return fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      });
    })
  );
});

async function handleOfflinePost(request) {
  try {
    return await fetch(request);
  } catch (err) {
    // Queue the request body for later sync.
    const body = await request.clone().text();
    const queue = await getOfflineQueue();
    queue.push({ body, url: request.url, ts: Date.now() });
    await setOfflineQueue(queue);
    await notifyClients('Arrival queued offline. Will sync when you reconnect.');
    return new Response(JSON.stringify({ success: true, queued: true, message: 'Arrival saved offline' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function getOfflineQueue() {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE, 'readonly');
    const store = tx.objectStore(OFFLINE_QUEUE);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function setOfflineQueue(items) {
  const db = await openQueueDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE, 'readwrite');
    const store = tx.objectStore(OFFLINE_QUEUE);
    store.clear();
    for (const item of items) store.put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function openQueueDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('ByaheroQueue', 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(OFFLINE_QUEUE, { keyPath: 'ts' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function notifyClients(message) {
  const clients = await self.clients.matchAll({ type: 'window' });
  for (const client of clients) {
    client.postMessage({ type: 'offline-queue', message });
  }
}

// Periodic sync of the offline queue.
self.addEventListener('sync', (event) => {
  if (event.tag === 'byahero-sync') {
    event.waitUntil(syncOfflineQueue());
  }
});

async function syncOfflineQueue() {
  const queue = await getOfflineQueue();
  if (!queue.length) return;
  for (const item of queue) {
    try {
      const res = await fetch(item.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: item.body
      });
      if (res.ok) {
        const remaining = queue.filter((q) => q.ts !== item.ts);
        await setOfflineQueue(remaining);
      }
    } catch (err) {
      // Still offline; stop trying.
      break;
    }
  }
}