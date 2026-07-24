/**
 * moments.js — Shared 7 demo moments definition
 *
 * Used by both PresentationMode.jsx and DemoController.jsx
 * to avoid the static+dynamic import warning.
 */

const MOMENTS = [
  { id: 'cv_gauging',   label: 'CV Gauging',     icon: '📷', color: '#00c9ff', shortLabel: 'CV' },
  { id: 'shap_xai',     label: 'SHAP XAI',       icon: '🧠', color: '#a855f7', shortLabel: 'XAI' },
  { id: 'causal',       label: 'Causal',         icon: '🔬', color: '#f59e0b', shortLabel: 'Causal' },
  { id: 'offline_acn',  label: 'Offline / ACN',  icon: '📶', color: '#ef4444', shortLabel: 'ACN' },
  { id: 'evacuation',   label: 'Evacuation',     icon: '🚌', color: '#22c55e', shortLabel: 'Evac' },
  { id: 'flood_ledger', label: 'FloodLedger',    icon: '🔗', color: '#3b82f6', shortLabel: 'Ledger' },
  { id: 'mirror',       label: 'MIRROR',         icon: '🔮', color: '#ec4899', shortLabel: 'Mirror' },
  { id: 'closing',      label: 'Closing',        icon: '🛡', color: '#00c9ff', shortLabel: 'Close' },
]

export default MOMENTS
