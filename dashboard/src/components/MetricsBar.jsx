import { riskColorHex } from '../utils/colorScale'

/**
 * Top metrics bar — system-wide stats + DEMO MODE toggle.
 */
export default function MetricsBar({
  predictions,
  activeAlerts,
  lastUpdated,
  stale,
  demoMode,
  onToggleDemo,
}) {
  const villageCount = predictions.length

  // Count distinct alert levels
  const warningCount = predictions.filter(
    (p) => p.alert_level === 'WARNING' || p.alert_level === 'EMERGENCY'
  ).length

  const maxRisk = predictions.reduce(
    (max, p) => Math.max(max, p.risk_score),
    0
  )

  const timeStr = lastUpdated
    ? lastUpdated.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—'

  return (
    <div className="h-12 bg-navy-light/90 backdrop-blur-md border-b border-white/10 flex items-center justify-between px-4 z-40">
      {/* Left — brand */}
      <div className="flex items-center gap-3">
        <h1 className="font-heading text-xl font-bold tracking-wider">
          <span className="text-accent">ARGUS</span>
          <span className="text-gray-500 text-sm ml-2 font-body font-normal">
            Flash Flood EWS
          </span>
        </h1>
      </div>

      {/* Center — stats */}
      <div className="flex items-center gap-6 text-xs font-body">
        <Stat label="Sensors" value="47" color="#00c9ff" />
        <Stat label="Villages" value={villageCount} color="#00c9ff" />
        <Stat
          label="Active Alerts"
          value={activeAlerts}
          color={activeAlerts > 0 ? '#ef4444' : '#22c55e'}
        />
        <Stat
          label="Max Risk"
          value={`${(maxRisk * 100).toFixed(0)}%`}
          color={riskColorHex(maxRisk)}
        />

        {/* System status */}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              stale ? 'bg-yellow-500 animate-pulse' : 'bg-green-500'
            }`}
          />
          <span className="text-gray-400">
            {stale ? 'STALE DATA' : demoMode ? 'DEMO MODE' : 'ONLINE'}
          </span>
        </div>

        <div className="text-gray-500">
          Updated: <span className="text-gray-300">{timeStr}</span>
        </div>
      </div>

      {/* Right — demo toggle */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleDemo}
          className={`px-3 py-1 rounded-md text-xs font-heading font-semibold uppercase tracking-wide transition-all ${
            demoMode
              ? 'bg-accent/20 text-accent border border-accent/40 animate-pulse-watch'
              : 'bg-navy-mid text-gray-400 border border-white/10 hover:border-accent/30 hover:text-white'
          }`}
        >
          {demoMode ? '⏸ Stop Demo' : '▶ Demo Mode'}
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value, color }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-gray-500">{label}:</span>
      <span className="font-semibold tabular-nums" style={{ color }}>
        {value}
      </span>
    </div>
  )
}
