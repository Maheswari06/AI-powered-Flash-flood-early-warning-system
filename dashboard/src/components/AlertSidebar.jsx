import { alertBadgeClass, alertLevelColor } from '../utils/colorScale'

/**
 * Live alert log sidebar — shows recent alerts in chronological order.
 */
export default function AlertSidebar({ alerts, loading }) {
  return (
    <div className="w-80 h-full bg-navy-light/90 backdrop-blur-md border-l border-white/10 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <h2 className="font-heading text-base font-bold text-accent tracking-wide">
          🚨 Alert Log
        </h2>
        <span className="text-xs text-gray-500 font-body">
          {alerts.length} event{alerts.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1.5">
        {loading && alerts.length === 0 && (
          <div className="text-center text-gray-500 text-sm py-8">
            Loading alerts...
          </div>
        )}

        {!loading && alerts.length === 0 && (
          <div className="text-center text-gray-600 text-sm py-8">
            No active alerts
          </div>
        )}

        {alerts.map((alert, idx) => (
          <AlertCard key={alert.id || idx} alert={alert} />
        ))}
      </div>
    </div>
  )
}

function AlertCard({ alert }) {
  const {
    village_id,
    village_name,
    alert_level,
    risk_score,
    timestamp,
    message,
  } = alert

  const displayName =
    village_name ||
    village_id
      ?.replace('VIL-HP-', '')
      .replace('VIL-AS-', '')
      .replace(/-/g, ' ') ||
    'Unknown'

  const timeStr = timestamp
    ? new Date(timestamp).toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : ''

  const borderColor = alertLevelColor(alert_level)
  const isUrgent = alert_level === 'WARNING' || alert_level === 'EMERGENCY'

  return (
    <div
      className={`rounded-lg px-3 py-2 border-l-3 ${
        isUrgent ? 'bg-red-950/30' : 'bg-navy-mid/50'
      }`}
      style={{ borderLeftColor: borderColor }}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-heading text-sm font-semibold text-white capitalize">
          {displayName}
        </span>
        <span className={alertBadgeClass(alert_level)}>{alert_level}</span>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-400">
          Risk:{' '}
          <span className="text-white font-medium">
            {(risk_score * 100).toFixed(0)}%
          </span>
        </span>
        <span className="text-gray-500">{timeStr}</span>
      </div>
      {message && (
        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{message}</p>
      )}
    </div>
  )
}
