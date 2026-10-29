/**
 * ByaHero PWA registration and offline queue handling.
 * Registers the service worker, registers background sync, and listens
 * for messages from the worker about queued arrivals.
 */
(function () {
  'use strict';

  if (!('serviceWorker' in navigator) || !('indexedDB' in window)) {
    return;
  }

  const SW_PATH = '/static/service-worker.js';
  const OFFLINE_QUEUE_KEY = 'byahero-offline-queue';

  let swRegistration = null;

  function showOfflineBanner(message) {
    let banner = document.getElementById('offline-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'offline-banner';
      banner.style.cssText =
        'position:fixed;bottom:0;left:0;right:0;background:#f59e0b;color:#fff;text-align:center;padding:8px;z-index:9999;font-size:14px;';
      document.body.appendChild(banner);
    }
    banner.textContent = message;
    banner.style.display = 'block';
  }

  function hideOfflineBanner() {
    const banner = document.getElementById('offline-banner');
    if (banner) banner.style.display = 'none';
  }

  function queueOfflineSubmission(body) {
    return new Promise((resolve, reject) => {
      const dbReq = indexedDB.open('ByaheroQueue', 1);
      dbReq.onupgradeneeded = () => {
        dbReq.result.createObjectStore(OFFLINE_QUEUE_KEY, { keyPath: 'ts' });
      };
      dbReq.onsuccess = () => {
        const db = dbReq.result;
        const tx = db.transaction(OFFLINE_QUEUE_KEY, 'readwrite');
        const store = tx.objectStore(OFFLINE_QUEUE_KEY);
        const item = { body: JSON.stringify(body), url: '/api/add-arrival-record', ts: Date.now() };
        store.put(item);
        tx.oncomplete = () => {
          // Ask the service worker to sync when possible.
          if (swRegistration && 'sync' in swRegistration) {
            swRegistration.sync.register('byahero-sync');
          }
          resolve(item);
        };
        tx.onerror = () => reject(tx.error);
      };
      dbReq.onerror = () => reject(dbReq.error);
    });
  }

  async function sendArrival(body) {
    try {
      const res = await fetch('/api/add-arrival-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (res.ok) return true;
    } catch (err) {
      // Offline — queue it.
    }
    await queueOfflineSubmission(body);
    showOfflineBanner('Arrival queued offline. Will sync when you reconnect.');
    return false;
  }

  window.ByaHeroPWA = {
    sendArrival: sendArrival,
    queueOfflineSubmission: queueOfflineSubmission
  };

  navigator.serviceWorker.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type === 'offline-queue' && data.message) {
      showOfflineBanner(data.message);
    }
  });

  navigator.serviceWorker.ready.then((reg) => {
    swRegistration = reg;
  });

  navigator.serviceWorker.register(SW_PATH).then((reg) => {
    swRegistration = reg;
    reg.addEventListener('updatefound', () => {
      const newSW = reg.installing;
      newSW.addEventListener('statechange', () => {
        if (newSW.state === 'installed' && navigator.serviceWorker.controller) {
          // New version available; prompt to refresh.
        }
      });
    });
  }).catch((err) => {
    // Registration failed — app still works online normally.
    console.warn('Service worker registration failed:', err);
  });
})();