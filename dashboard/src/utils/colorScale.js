/**
 * Risk score → RGBA color mapping for Deck.gl layers.
 *
 * Threshold bands (NDMA-aligned):
 *   [0.00, 0.35) → green  (NORMAL)
 *   [0.35, 0.55) → yellow (ADVISORY)
 *   [0.55, 0.72) → orange (WATCH)
 *   [0.72, 1.00] → red    (WARNING / EMERGENCY)
 */

/** Deck.gl RGBA [r, g, b, a] — values 0-255 */
export function riskColorRGBA(score) {
  if (score < 0.35) return [34, 197, 94, 180]   // green
  if (score < 0.55) return [234, 179, 8, 180]    // yellow
  if (score < 0.72) return [249, 115, 22, 180]   // orange
  return [239, 68, 68, 200]                       // red
}

/** CSS hex color string */
export function riskColorHex(score) {
  if (score < 0.35) return '#22c55e'
  if (score < 0.55) return '#eab308'
  if (score < 0.72) return '#f97316'
  if (score < 0.88) return '#ef4444'
  return '#dc2626'
}

/** CSS class name for Tailwind */
export function riskColorClass(score) {
  if (score < 0.35) return 'text-risk-normal'
  if (score < 0.55) return 'text-risk-advisory'
  if (score < 0.72) return 'text-risk-watch'
  if (score < 0.88) return 'text-risk-warning'
  return 'text-risk-emergency'
}

/** Alert level string → CSS hex */
export function alertLevelColor(level) {
  const map = {
    NORMAL: '#22c55e',
    ADVISORY: '#eab308',
    WATCH: '#f97316',
    WARNING: '#ef4444',
    EMERGENCY: '#dc2626',
  }
  return map[level] || '#6b7280'
}

/** Alert level → bg class with appropriate animation */
export function alertBadgeClass(level) {
  const base = 'px-2 py-0.5 rounded text-xs font-heading font-semibold uppercase'
  const map = {
    NORMAL: `${base} bg-risk-normal/20 text-risk-normal`,
    ADVISORY: `${base} bg-risk-advisory/20 text-risk-advisory`,
    WATCH: `${base} bg-risk-watch/20 text-risk-watch animate-pulse-watch`,
    WARNING: `${base} bg-risk-warning/20 text-risk-warning animate-pulse-emergency`,
    EMERGENCY: `${base} bg-risk-emergency/20 text-risk-emergency animate-pulse-emergency`,
  }
  return map[level] || `${base} bg-gray-700 text-gray-400`
}

/** Village dot radius based on risk (Deck.gl pixels) */
export function riskRadius(score) {
  return 6 + score * 18  // 6px normal → 24px emergency
}
