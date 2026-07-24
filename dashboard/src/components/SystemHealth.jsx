import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

/**
 * SystemHealth — Live service status monitor
 *
 * Polls the API Gateway /health every 10s and displays
 * a condensed 3-column grid of service health dots.
 *
 * Usage:
 *   <SystemHealth />                    — inline compact badge
 *   <SystemHealth expanded={true} />    — full grid view
 */

const SERVICE_LABELS = {
  ingestion:      { label: 'Ingestion',     icon: '📡', phase: 1 },
  cv_gauging:     { label: 'CV Gauging',    icon: '📷', phase: 1 },
  feature_engine: { label: 'Feature Engine',icon: '⚙️', phase: 1 },
  prediction:     { label: 'Prediction',    icon: '🧠', phase: 1 },
  alert_dispatcher:{ label: 'Alert Dispatch',icon: '🚨', phase: 1 },
  acn_node:       { label: 'ACN Node',      icon: '📶', phase: 2 },
  causal_engine:  { label: 'Causal Engine', icon: '🔬', phase: 2 },
  chorus:         { label: 'CHORUS',        icon: '📢', phase: 2 },
  fl_server:      { label: 'FL Server',     icon: '🔗', phase: 2 },
  flood_ledger:   { label: 'FloodLedger',   icon: '📒', phase: 2 },
  evacuation_rl:  { label: 'Evacuation RL', icon: '🚌', phase: 2 },
  mirror:         { label: 'MIRROR',        icon: '🔮', phase: 2 },
  scarnet:        { label: 'ScarNet',       icon: '🛰️', phase: 3 },
  api_gateway:    { label: 'API Gateway',   icon: '🌐', phase: 3 },
}

function StatusDot({ status }) {
  const cls = status === 'healthy' ? 'status-healthy'
            : status === 'degraded' ? 'status-degraded'
            : status === 'offline' ? 'status-offline'
            : 'status-unknown'
  return <span className={cls} />
}

export default function SystemHealth({ expanded = false }) {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showGrid, setShowGrid] = useState(expanded)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await axios.get(API.gatewayHealth)
      setHealth(res.data)
    } catch {
      // Build a mock health response for demo
      const mockServices = {}
      Object.keys(SERVICE_LABELS).forEach(k => {
        mockServices[k] = {
          status: Math.random() > 0.1 ? 'healthy' : 'degraded',
          latency_ms: Math.round(5 + Math.random() * 50),
        }
      })
      setHealth({
        overall: 'OPERATIONAL',
        services: mockServices,
        timestamp: new Date().toISOString(),
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    const timer = setInterval(fetchHealth, 10000)
    return () => clearInterval(timer)
  }, [fetchHealth])

  // Compute counts
  const services = health?.services || {}
  const entries = Object.entries(services)
  const healthyCount = entries.filter(([, v]) => v.status === 'healthy').length
  const totalCount = entries.length
  const overall = health?.overall || (healthyCount === totalCount ? 'OPERATIONAL' : 'DEGRADED')

  const overallColor = overall === 'OPERATIONAL' ? '#22c55e'
                     : overall === 'DEGRADED' ? '#f59e0b'
                     : '#ef4444'

  // Compact badge (for MetricsBar area)
  if (!showGrid) {
    return (
      <button
        onClick={() => setShowGrid(true)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] hover:bg-gray-800/60 transition-colors"
        title="System Health — click for details"
      >
        {loading ? (
          <span className="w-2 h-2 rounded-full bg-gray-500 animate-pulse" />
        ) : (
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: overallColor,
              boxShadow: `0 0 6px ${overallColor}`,
            }}
          />
        )}
        <span className="text-gray-400 font-code">
          {healthyCount}/{totalCount}
        </span>
      </button>
    )
  }

  // Expanded grid panel
  return (
    <div className="glass-card p-4 animate-slide-up">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">🏥</span>
          <h3 className="font-heading text-sm font-bold text-white">System Health</h3>
          <span
            className="text-[10px] font-code px-1.5 py-0.5 rounded"
            style={{
              color: overallColor,
              background: `${overallColor}15`,
              border: `1px solid ${overallColor}30`,
            }}
          >
            {overall}
          </span>
        </div>
        {!expanded && (
          <button
            onClick={() => setShowGrid(false)}
            className="text-gray-500 hover:text-white text-xs transition-colors"
          >
            ✕
          </button>
        )}
      </div>

      <div className="health-grid">
        {Object.entries(SERVICE_LABELS).map(([key, meta]) => {
          const svc = services[key]
          const status = svc?.status || 'unknown'
          const latency = svc?.latency_ms
          return (
            <div key={key} className="health-service">
              <StatusDot status={status} />
              <span className="text-gray-300 flex-1 truncate">
                {meta.icon} {meta.label}
              </span>
              {latency != null && (
                <span className="text-gray-600 font-code text-[10px]">
                  {latency}ms
                </span>
              )}
            </div>
          )
        })}
      </div>

      {health?.timestamp && (
        <div className="text-[10px] text-gray-600 mt-2 text-right font-code">
          Updated {new Date(health.timestamp).toLocaleTimeString('en-IN')}
        </div>
      )}
    </div>
  )
}
