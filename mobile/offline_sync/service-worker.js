/**
 * ARGUS PWA — Enhanced Service Worker
 * Workbox-powered with push notifications and background sync.
 *
 * This file is used as a custom service-worker source for vite-plugin-pwa.
 * It extends default precaching with:
 *   - Push notification handling (vibrate pattern by alert level)
 *   - Background sync for CHORUS flood reports
 *   - Offline-first caching strategies
 */
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, CacheFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { BackgroundSyncPlugin } from 'workbox-background-sync';

/* ── Precache manifest (injected by vite-plugin-pwa) ────── */
precacheAndRoute(self.__WB_MANIFEST || []);
cleanupOutdatedCaches();

/* ── API caching strategies ─────────────────────────────── */

// Predictions — network-first with 5s timeout, fall back to cache
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/predictions'),
  new NetworkFirst({
    cacheName: 'argus-predictions',
    networkTimeoutSeconds: 5,
    plugins: [
      new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 3600 }),
    ],
  }),
);

// Evacuation plans — network-first
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/evacuation'),
  new NetworkFirst({
    cacheName: 'argus-evacuation',
    networkTimeoutSeconds: 5,
    plugins: [
      new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 86400 }),
    ],
  }),
);

// CHORUS reports — background sync queue
const bgSyncPlugin = new BackgroundSyncPlugin('chorus-report-queue', {
  maxRetentionTime: 24 * 60, // 24 hours
  onSync: async ({ queue }) => {
    let entry;
    while ((entry = await queue.shiftRequest())) {
      try {
        await fetch(entry.request.clone());
      } catch (err) {
        await queue.unshiftRequest(entry);
        throw err;
      }
    }
  },
});

registerRoute(
  ({ url }) => url.pathname.startsWith('/api/chorus/report'),
  new NetworkFirst({
    cacheName: 'argus-reports',
    plugins: [bgSyncPlugin],
  }),
  'POST',
);

// Static assets — cache-first
registerRoute(
  ({ request }) =>
    request.destination === 'image' ||
    request.destination === 'font' ||
    request.destination === 'style',
  new CacheFirst({
    cacheName: 'argus-static',
    plugins: [
      new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 30 * 24 * 3600 }),
    ],
  }),
);

// Village / alert data — stale-while-revalidate
registerRoute(
  ({ url }) =>
    url.pathname.startsWith('/api/alerts') ||
    url.pathname.startsWith('/api/evacuation/villages'),
  new StaleWhileRevalidate({
    cacheName: 'argus-metadata',
    plugins: [
      new ExpirationPlugin({ maxEntries: 30, maxAgeSeconds: 3600 }),
    ],
  }),
);

/* ── Map tile caching (OSM / CartoDB / ESRI — offline maps) ── */

// Cache map tiles for offline use — CacheFirst with 7-day expiry
registerRoute(
  ({ url }) =>
    url.hostname.includes('tile.openstreetmap.org') ||
    url.hostname.includes('basemaps.cartocdn.com') ||
    url.hostname.includes('arcgisonline.com') ||
    url.hostname.includes('tile.opentopomap.org'),
  new CacheFirst({
    cacheName: 'map-tiles-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 500,
        maxAgeSeconds: 7 * 24 * 3600, // 7 days
      }),
    ],
  }),
);

/* ── Push notification handler ──────────────────────────── */

const VIBRATE_PATTERNS = {
  NORMAL:    [100],
  WATCH:     [200, 100, 200],
  WARNING:   [300, 100, 300, 100, 300],
  DANGER:    [500, 200, 500, 200, 500],
  EMERGENCY: [1000, 300, 1000, 300, 1000, 300, 1000],
};

const ALERT_ICONS = {
  NORMAL:    '/pwa/icons/alert-normal.png',
  WATCH:     '/pwa/icons/alert-watch.png',
  WARNING:   '/pwa/icons/alert-warning.png',
  DANGER:    '/pwa/icons/alert-danger.png',
  EMERGENCY: '/pwa/icons/alert-emergency.png',
};

self.addEventListener('push', (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = {
      title: 'ARGUS Alert',
      body: event.data.text(),
      alert_level: 'WATCH',
    };
  }

  const level = payload.alert_level || 'WATCH';
  const isEmergency = level === 'EMERGENCY' || level === 'DANGER';

  const options = {
    body: payload.body || `Alert level: ${level}`,
    icon: ALERT_ICONS[level] || '/pwa/icons/icon-192.png',
    badge: '/pwa/icons/badge-72.png',
    vibrate: VIBRATE_PATTERNS[level] || VIBRATE_PATTERNS.WATCH,
    tag: `argus-alert-${payload.station_id || 'general'}`,
    renotify: true,
    requireInteraction: isEmergency,
    data: {
      url: payload.url || '/pwa/',
      alert_level: level,
      village_id: payload.village_id,
      station_id: payload.station_id,
    },
    actions: isEmergency
      ? [
          { action: 'evacuate', title: 'View Evacuation Plan' },
          { action: 'dismiss',  title: 'Dismiss' },
        ]
      : [
          { action: 'view',    title: 'View Details' },
          { action: 'dismiss', title: 'Dismiss' },
        ],
  };

  event.waitUntil(
    self.registration.showNotification(
      payload.title || `ARGUS: ${level} Alert`,
      options,
    ),
  );
});

/* ── Notification click handler ─────────────────────────── */

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const data = event.notification.data || {};
  let targetUrl = data.url || '/pwa/';

  if (event.action === 'evacuate') {
    targetUrl = '/pwa/evacuation';
  } else if (event.action === 'view') {
    targetUrl = '/pwa/';
  } else if (event.action === 'dismiss') {
    return;
  }

  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        // Focus existing window if open
        for (const client of clients) {
          if (client.url.includes('/pwa') && 'focus' in client) {
            client.navigate(targetUrl);
            return client.focus();
          }
        }
        // Otherwise open new window
        return self.clients.openWindow(targetUrl);
      }),
  );
});

/* ── Skip waiting + clients claim for instant activation ── */

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
