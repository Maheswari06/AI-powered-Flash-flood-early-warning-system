/**
 * IndexedDB helpers for ARGUS PWA offline storage.
 * Uses the `idb` library for promise-based access.
 */
import { openDB } from 'idb';

const DB_NAME = 'argus-pwa';
const DB_VERSION = 1;

const STORES = {
  village:     'village',
  predictions: 'predictions',
  evacuation:  'evacuation',
  reports:     'pendingReports',
};

async function getDB() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORES.village)) {
        db.createObjectStore(STORES.village);
      }
      if (!db.objectStoreNames.contains(STORES.predictions)) {
        db.createObjectStore(STORES.predictions, { keyPath: 'station_id' });
      }
      if (!db.objectStoreNames.contains(STORES.evacuation)) {
        db.createObjectStore(STORES.evacuation, { keyPath: 'village_id' });
      }
      if (!db.objectStoreNames.contains(STORES.reports)) {
        db.createObjectStore(STORES.reports, { keyPath: 'id', autoIncrement: true });
      }
    },
  });
}

/* ── Village preference ─────────────────────────────────── */
export async function saveVillageToIDB(village) {
  const db = await getDB();
  await db.put(STORES.village, village, 'selected');
}

export async function loadSavedVillage() {
  const db = await getDB();
  return db.get(STORES.village, 'selected');
}

/* ── Prediction cache ───────────────────────────────────── */
export async function cachePredictions(predictions) {
  const db = await getDB();
  const tx = db.transaction(STORES.predictions, 'readwrite');
  for (const p of predictions) {
    await tx.store.put(p);
  }
  await tx.done;
}

export async function getCachedPredictions() {
  const db = await getDB();
  return db.getAll(STORES.predictions);
}

/* ── Evacuation plan cache ──────────────────────────────── */
export async function cacheEvacPlan(plan) {
  const db = await getDB();
  await db.put(STORES.evacuation, plan);
}

export async function getCachedEvacPlan(villageId) {
  const db = await getDB();
  return db.get(STORES.evacuation, villageId);
}

/* ── Pending flood reports (background-sync queue) ──────── */
export async function queueReport(report) {
  const db = await getDB();
  await db.add(STORES.reports, { ...report, queued_at: Date.now() });
}

export async function getPendingReports() {
  const db = await getDB();
  return db.getAll(STORES.reports);
}

export async function clearReport(id) {
  const db = await getDB();
  await db.delete(STORES.reports, id);
}
