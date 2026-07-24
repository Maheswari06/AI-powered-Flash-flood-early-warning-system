/**
 * EvacuationMap — Phase 2 enhanced evacuation planning dashboard.
 *
 * Full-screen mode with vehicle assignments, road closure warnings,
 * shelter capacity bars, per-village cards, and bottom stats bar.
 */

import { useState, useEffect, useCallback } from 'react'
import useEvacuationPlan from '../hooks/useEvacuationPlan'

const VEHICLE_ICONS = { bus: '🚌', truck: '🚛', boat: '🚤', helicopter: '🚁' }
const PRIORITY_COLORS = ['', 'text-red-400', 'text-orange-400', 'text-yellow-400', 'text-blue-400']
const STATUS_BADGES = {
  pending: { bg: 'bg-amber-900/40', text: 'text-amber-400', label: 'PENDING' },
  in_transit: { bg: 'bg-blue-900/40', text: 'text-blue-400', label: 'IN TRANSIT' },
  completed: { bg: 'bg-green-900/40', text: 'text-green-400', label: 'COMPLETE' },
  blocked: { bg: 'bg-red-900/40', text: 'text-red-400', label: 'BLOCKED' },
}

export default function EvacuationMap({ selectedVillage = 'kullu_01', riskScore = 0, demoMode = false, fullScreen = false }) {
  const { plan, notifications, loading, triggerDemo, recompute } = useEvacuationPlan(demoMode)
  const [expanded, setExpanded] = useState(true)
  const [selectedAssignment, setSelectedAssignment] = useState(null)
  const [showNotifications, setShowNotifications] = useState(false)

  // Compact overlay mode (when not fullScreen)
  if (!fullScreen) {
    if (!expanded) {
      return (
        <button
          onClick={() => setExpanded(true)}
          className="bg-navy/90 border border-gray-700 text-accent text-xs font-mono px-3 py-2 rounded-lg hover:border-accent transition-colors"
        >
          EVAC MAP ▸
        </button>
      )
    }

    return (
      <div className="bg-navy/95 backdrop-blur-sm border border-gray-700 rounded-xl p-4 max-w-sm">
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-display text-sm text-white tracking-wider">EVACUATION MAP</h3>
          <button onClick={() => setExpanded(false)} className="text-gray-500 text-xs hover:text-white">✕</button>
        </div>
        <div className="text-xs text-gray-400">
          {plan ? `${plan.total_people_covered || 0} people · ${plan.assignments?.length || 0} routes` : 'No active plan'}
        </div>
      </div>
    )
  }

  // ── Full-screen mode ──────────────────────────────────────────────
  return (
    <div className="flex-1 flex bg-navy">
      {/* Left sidebar — Village assignment cards */}
      <div className="w-80 border-r border-gray-800 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-display text-white tracking-wider text-sm">
              🚌 EVACUATION PLANNER
            </h2>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
              plan?.planner_mode === 'ppo' ? 'bg-purple-900/50 text-purple-400' : 'bg-blue-900/50 text-blue-400'
            }`}>
              {plan?.planner_mode?.toUpperCase() || 'OFFLINE'}
            </span>
          </div>

          {/* Action buttons */}
          <div className="flex gap-2">
            <button
              onClick={triggerDemo}
              disabled={loading}
              className="flex-1 text-[10px] font-mono bg-accent/20 text-accent border border-accent/40 rounded px-2 py-1.5 hover:bg-accent/30 disabled:opacity-50 transition-colors"
            >
              {loading ? '⟳ COMPUTING...' : '▶ RUN DEMO'}
            </button>
            <button
              onClick={recompute}
              disabled={loading}
              className="text-[10px] font-mono text-gray-400 border border-gray-700 rounded px-2 py-1.5 hover:border-accent hover:text-accent disabled:opacity-50 transition-colors"
            >
              ⟳
            </button>
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className={`text-[10px] font-mono border rounded px-2 py-1.5 transition-colors ${
                showNotifications
                  ? 'text-amber-400 border-amber-700 bg-amber-900/20'
                  : 'text-gray-400 border-gray-700 hover:border-amber-500'
              }`}
            >
              🔔 {notifications.length}
            </button>
          </div>
        </div>

        {/* Notifications panel */}
        {showNotifications && notifications.length > 0 && (
          <div className="border-b border-gray-800 max-h-48 overflow-y-auto">
            {notifications.map((n, i) => (
              <div key={i} className={`px-3 py-2 border-b border-gray-800/50 text-[10px] ${
                n.level === 'CRITICAL' ? 'bg-red-900/10 text-red-300' :
                n.level === 'URGENT' ? 'bg-orange-900/10 text-orange-300' :
                'text-gray-400'
              }`}>
                {n.message}
              </div>
            ))}
          </div>
        )}

        {/* Assignment cards */}
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {plan?.assignments?.map((a, i) => {
            const badge = STATUS_BADGES[a.status] || STATUS_BADGES.pending
            const isSelected = selectedAssignment === i
            return (
              <div
                key={`${a.village_id}-${a.vehicle_id}`}
                onClick={() => setSelectedAssignment(isSelected ? null : i)}
                className={`rounded-lg border p-3 cursor-pointer transition-all ${
                  isSelected
                    ? 'border-accent bg-accent/10 shadow-lg shadow-accent/5'
                    : 'border-gray-700 bg-gray-800/30 hover:border-gray-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-bold ${PRIORITY_COLORS[a.priority] || 'text-white'}`}>
                      P{a.priority}
                    </span>
                    <span className="text-xs text-white font-medium">{a.village_name || a.village_id}</span>
                  </div>
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${badge.bg} ${badge.text}`}>
                    {badge.label}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
                  <div className="text-gray-400">
                    {VEHICLE_ICONS[a.vehicle_type] || '🚐'} {a.vehicle_id}
                  </div>
                  <div className="text-gray-400">
                    👥 {a.population?.toLocaleString()} people
                  </div>
                  <div className="text-gray-400">
                    🛣️ {a.route_id}
                  </div>
                  <div className="text-gray-400">
                    🏠 {a.shelter_id}
                  </div>
                  <div className="text-cyan-400 font-mono">
                    ETA {a.eta_minutes} min
                  </div>
                  <div className="text-gray-500">
                    {a.trips_needed} trips
                  </div>
                </div>

                {a.road_closure_warning && (
                  <div className="mt-1.5 text-[9px] text-amber-400 bg-amber-900/20 rounded px-2 py-1">
                    ⚠️ Road closure imminent — depart before cutoff
                  </div>
                )}

                {isSelected && (
                  <div className="mt-2 pt-2 border-t border-gray-700 text-[9px] text-gray-500">
                    <div>Departure cutoff: {a.departure_cutoff_utc ? new Date(a.departure_cutoff_utc).toLocaleTimeString() : '—'}</div>
                    <div>Trips needed: {a.trips_needed} (vehicle cap: {a.population && a.trips_needed ? Math.ceil(a.population / a.trips_needed) : '—'})</div>
                  </div>
                )}
              </div>
            )
          })}

          {(!plan || !plan.assignments?.length) && (
            <div className="text-center py-8">
              <div className="text-3xl mb-2">🚌</div>
              <div className="text-xs text-gray-500">No active evacuation plan</div>
              <div className="text-[10px] text-gray-600 mt-1">Click "RUN DEMO" to simulate Majuli Island scenario</div>
            </div>
          )}
        </div>
      </div>

      {/* Main content area — Stats + Map placeholder */}
      <div className="flex-1 flex flex-col">
        {/* Map placeholder */}
        <div className="flex-1 relative bg-gray-900/50 flex items-center justify-center">
          <div className="text-center">
            <div className="text-6xl mb-4">🗺️</div>
            <div className="text-gray-400 text-sm font-display tracking-wider">EVACUATION MAP</div>
            <div className="text-gray-600 text-xs mt-2">Leaflet + OpenStreetMap — routes, vehicles, shelters</div>
            {plan && (
              <div className="mt-4 grid grid-cols-2 gap-3 max-w-sm mx-auto">
                {plan.assignments?.map((a, i) => (
                  <div key={i} className="bg-gray-800/60 rounded-lg p-2 text-left">
                    <div className="text-[10px] text-gray-500">{a.village_name || a.village_id}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-sm">{VEHICLE_ICONS[a.vehicle_type] || '🚐'}</span>
                      <span className="text-xs text-white">→ {a.shelter_id}</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-1 mt-1.5">
                      <div
                        className="bg-accent h-1 rounded-full transition-all"
                        style={{ width: `${Math.min(100, (1 - a.eta_minutes / 120) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Bottom stats bar */}
        {plan && (
          <div className="border-t border-gray-800 bg-gray-900/80 px-6 py-3 flex items-center gap-6">
            <div>
              <div className="text-2xl text-white font-mono font-bold">
                {plan.total_people_covered?.toLocaleString() || 0}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">People Covered</div>
            </div>
            <div>
              <div className="text-2xl text-cyan-400 font-mono font-bold">
                {plan.estimated_completion_minutes || '—'}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">Est. Minutes</div>
            </div>
            <div>
              <div className="text-2xl text-accent font-mono font-bold">
                {plan.vehicles_deployed || 0}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">Vehicles</div>
            </div>
            <div>
              <div className="text-2xl text-green-400 font-mono font-bold">
                {plan.shelters_used || 0}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">Shelters</div>
            </div>
            <div className="ml-auto">
              <div className="text-lg text-white font-mono">
                {plan.confidence ? `${(plan.confidence * 100).toFixed(0)}%` : '—'}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider">Confidence</div>
            </div>
            <div>
              <div className={`text-sm font-mono px-2 py-1 rounded ${
                plan.planner_mode === 'ppo' ? 'bg-purple-900/40 text-purple-400' : 'bg-blue-900/40 text-blue-400'
              }`}>
                {plan.planner_mode?.toUpperCase() || 'OFFLINE'}
              </div>
              <div className="text-[9px] text-gray-500 uppercase tracking-wider mt-0.5">Planner</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
