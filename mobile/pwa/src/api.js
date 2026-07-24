/**
 * API client for ARGUS PWA.
 * Falls back to IndexedDB cache when offline.
 */
import { cachePredictions, getCachedPredictions, cacheEvacPlan, getCachedEvacPlan, queueReport } from './db';

const API_BASE = '/api';

/* ── Generic fetch with offline fallback ────────────────── */
async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

/* ── Risk data for a village ────────────────────────────── */
export async function fetchRiskData(villageId) {
  try {
    const data = await apiFetch(`/predictions/village/${villageId}`);
    // Cache for offline use
    if (data.predictions) {
      await cachePredictions(data.predictions);
    }
    return { ...data, fromCache: false };
  } catch (err) {
    // Offline fallback
    const cached = await getCachedPredictions();
    if (cached.length > 0) {
      return {
        predictions: cached,
        alert_level: cached[0]?.alert_level || 'NORMAL',
        fromCache: true,
      };
    }
    throw err;
  }
}

/* ── SHAP feature explanations ──────────────────────────── */
export async function fetchExplanation(stationId) {
  return apiFetch(`/predictions/explain/${stationId}`);
}

/* ── Evacuation plan ────────────────────────────────────── */
export async function fetchEvacPlan(villageId) {
  try {
    const data = await apiFetch(`/evacuation/plan/${villageId}`);
    await cacheEvacPlan({ village_id: villageId, ...data });
    return { ...data, fromCache: false };
  } catch (err) {
    const cached = await getCachedEvacPlan(villageId);
    if (cached) return { ...cached, fromCache: true };
    throw err;
  }
}

/* ── Submit flood report (crowd-sourced CHORUS) ─────────── */
export async function submitFloodReport(report) {
  try {
    return await apiFetch('/chorus/report', {
      method: 'POST',
      body: JSON.stringify(report),
    });
  } catch (err) {
    // Queue for background sync when back online
    await queueReport(report);
    return { queued: true, message: 'Report saved — will send when online' };
  }
}

/* ── Push notification subscription ─────────────────────── */
export async function subscribeToPushNotifications(subscription, villageId) {
  return apiFetch('/notifications/subscribe', {
    method: 'POST',
    body: JSON.stringify({ subscription, village_id: villageId }),
  });
}

/* ── Available villages / stations ──────────────────────── */
export async function fetchVillages(basinId) {
  return apiFetch(`/evacuation/villages${basinId ? `?basin=${basinId}` : ''}`);
}

/* ── Alert history ──────────────────────────────────────── */
export async function fetchAlertHistory(villageId) {
  return apiFetch(`/alerts/history/${villageId}`);
}
