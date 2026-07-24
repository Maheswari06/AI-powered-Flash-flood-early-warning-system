/**
 * api.js — Single source of truth for every backend URL
 *
 * The Vite dev-server proxy (vite.config.js) forwards each
 * prefix to the correct service port, so we only need relative paths.
 *
 * In production, the API Gateway (port 8000) would aggregate these.
 */

const API = Object.freeze({
  // ── Phase 1 ──────────────────────────────────
  predictions: '/api/v1/predictions/all',
  alertLog:    '/api/v1/alert/log',

  // ── Phase 2 ──────────────────────────────────
  causalRisk:  (villageId) => `/api/v1/causal/risk/${villageId}`,
  causalIntervene: '/api/v1/causal/intervene',

  chorusStats: '/api/v1/chorus/stats',
  chorusDemoGenerate: (villageId, count = 5) =>
    `/api/v1/chorus/demo/generate?village_id=${villageId}&count=${count}`,
  chorusWS: `ws://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:8008/ws/signals`,

  evacPlan:    (scenarioId) => `/api/v1/evacuation/plan/${scenarioId}`,
  evacNotify:  '/api/v1/evacuation/notifications',
  evacDemo:    '/api/v1/evacuation/demo',
  evacCompute: '/api/v1/evacuation/compute',

  flStatus:    '/api/v1/fl/status',

  ledgerSummary: '/api/v1/ledger/chain/summary',
  ledgerChain:   '/api/v1/ledger/chain',
  ledgerVerify:  '/api/v1/ledger/verify',
  ledgerDemoFlood: (villageId) =>
    `/api/v1/ledger/demo/flood?village_id=${villageId}`,

  mirrorCF:     (eventId) => `/api/v1/mirror/event/${eventId}/counterfactuals`,
  mirrorCustom: (eventId) => `/api/v1/mirror/event/${eventId}/custom`,
  mirrorReport: (eventId) => `/api/v1/mirror/event/${eventId}/report`,

  // ── Phase 3 ──────────────────────────────────
  scarnetLatest:   '/api/v1/scarnet/latest',
  scarnetTrigger:  '/api/v1/scarnet/trigger-demo',
  scarnetHistory:  (id) => `/api/v1/scarnet/history/${id}`,
  scarnetTiles:    { before: '/api/v1/scarnet/tiles/before', after: '/api/v1/scarnet/tiles/after' },
  scarnetRiskDelta:(id) => `/api/v1/scarnet/risk-delta/${id}`,

  // API Gateway aggregated endpoints
  dashboardSnapshot: '/api/v1/dashboard/snapshot',
  gatewayHealth:     '/api/v1/dashboard/health',

  // Model Monitor
  monitorDrift:      '/api/v1/monitor/drift-report',
  monitorAccuracy:   '/api/v1/monitor/accuracy-history',
  monitorRetrain:    '/api/v1/monitor/retrain',
  monitorHealth:     '/api/v1/monitor/health',

  // ── Phase 7 — Gap Closure ──────────────────
  droneActive:       '/api/v1/drone/active',
  droneDemoTrigger:  '/api/v1/drone/demo-trigger',
  droneReadings:     (droneId) => `/api/v1/drone/${droneId}/readings`,

  ndmaBulletins:     '/api/v1/ndma/bulletins',
  ndmaCompliance:    '/api/v1/ndma/compliance-check',
  ndmaAlertLevels:   '/api/v1/ndma/alert-levels',

  iotDevices:        '/api/v1/iot/devices',
  iotProtocols:      '/api/v1/iot/protocols',
  iotDemoBurst:      '/api/v1/iot/demo-burst',

  flashFloodActive:  '/api/v1/flash-flood/active',
  flashFloodCheck:   '/api/v1/flash-flood/check',

  displacementSummary: '/api/v1/displacement/summary',
  displacementShelters:'/api/v1/displacement/shelters',
  displacementFlows:   '/api/v1/displacement/flows',

  cellBroadcastAlerts: '/api/v1/cell-broadcast/alerts',
})

export default API
