/**
 * ARGUS PWA — Unified Storage Utilities
 *
 * Re-exports IndexedDB helpers and push notification subscription
 * from a single entry point for convenience.
 *
 * Primary implementations:
 *   - db.js:  IndexedDB CRUD (village, predictions, evacuation, reports)
 *   - api.js: Push notification subscription via backend
 */
export {
  loadSavedVillage,
  saveVillageToIDB,
  cachePredictions,
  getCachedPredictions,
  cacheEvacPlan,
  getCachedEvacPlan,
  queueReport,
  getPendingReports,
  clearReport,
} from '../db';

export { subscribeToPushNotifications } from '../api';
