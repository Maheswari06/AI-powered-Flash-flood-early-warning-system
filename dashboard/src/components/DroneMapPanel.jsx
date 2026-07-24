import { useState, useEffect } from 'react'

/**
 * DroneMapPanel — Real-time drone surveillance + gauging results
 *
 * Gap 1 closure: Active drone fleet status, mission tracking,
 * and CV-based water level readings from drone imagery.
 *
 * Wired to:
 *   GET  /api/v1/drone/active         (DroneStream service)
 *   POST /api/v1/drone/demo-trigger   (Demo flight simulation)
 *   GET  /api/v1/gauges/active        (Gateway aggregation)
 */

const MISSION_STYLES = {
  FLOOD_RECON:   { bg: 'bg-blue-900/40',   text: 'text-blue-300',   border: 'border-blue-600/30' },
  GAUGE_SURVEY:  { bg: 'bg-purple-900/40',  text: 'text-purple-300', border: 'border-purple-600/30' },
  SEARCH_RESCUE: { bg: 'bg-red-900/40',     text: 'text-red-300',    border: 'border-red-600/30' },
}

const STATUS_DOT = {
  ACTIVE:       'bg-green-400',
  REGISTERED:   'bg-yellow-400',
  DEMO_STANDBY: 'bg-blue-400',
  OFFLINE:      'bg-slate-500',
}

const DroneMapPanel = () => {
  const [drones, setDrones] = useState([])
  const [lastResult, setLastResult] = useState(null)
  const [gauges, setGauges] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [dRes, gRes] = await Promise.allSettled([
          fetch('/api/v1/drone/active'),
          fetch('/api/v1/gauges/active'),
        ])
        if (dRes.status === 'fulfilled' && dRes.value.ok) {
          const dData = await dRes.value.json()
          setDrones(dData.drones || [])
        }
        if (gRes.status === 'fulfilled' && gRes.value.ok) {
          const gData = await gRes.value.json()
          setGauges(gData.gauges || [])
        }
      } catch { /* ignore */ }
      setLoading(false)
    }
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [])

  const triggerDemo = async () => {
    try {
      const res = await fetch('/api/v1/drone/demo-trigger', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setLastResult(data)
      }
    } catch { /* ignore */ }
  }

  return (
    <div className="bg-slate-900 rounded-2xl p-5 border border-cyan-900/50">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-cyan-400 font-heading font-bold text-xl">
            DroneStream Surveillance
          </h2>
          <p className="text-slate-500 text-xs mt-0.5">
            CV-based water level gauging from drone imagery
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full text-xs font-bold bg-blue-900/40 text-blue-300 border border-blue-600/30">
            {drones.length} drones
          </span>
          <button
            onClick={triggerDemo}
            className="px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
          >
            Demo Flight
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-14 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          {/* Active drones */}
          <div className="mb-4">
            <h3 className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
              Active Fleet
            </h3>
            <div className="space-y-2">
              {drones.length === 0 ? (
                <p className="text-slate-600 text-sm text-center py-4">
                  No active drones. Click "Demo Flight" to simulate.
                </p>
              ) : (
                drones.map((d, i) => {
                  const mission = MISSION_STYLES[d.mission_type] || MISSION_STYLES.FLOOD_RECON
                  return (
                    <div key={i} className="bg-slate-800/60 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-2 h-2 rounded-full ${STATUS_DOT[d.status] || 'bg-slate-500'}`} />
                        <span className="text-slate-200 text-sm font-bold flex-1">{d.drone_id}</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${mission.bg} ${mission.text} border ${mission.border}`}>
                          {d.mission_type?.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        <span>Type: {d.drone_type}</span>
                        <span>Basin: {d.basin_id}</span>
                        {d.last_lat && <span>Pos: {d.last_lat?.toFixed(3)}, {d.last_lon?.toFixed(3)}</span>}
                        {d.last_alt && <span>Alt: {d.last_alt}m</span>}
                        <span>Frames: {d.frames_processed || 0}</span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Latest gauging result */}
          {lastResult && (
            <div className="mb-4 bg-blue-900/20 rounded-xl p-4 border border-blue-600/30">
              <h3 className="text-blue-400 text-xs font-bold uppercase tracking-wider mb-3">
                Latest Drone Gauging Result
              </h3>
              <div className="grid grid-cols-4 gap-3 mb-3">
                <div className="text-center">
                  <p className="text-slate-400 text-xs">Water Depth</p>
                  <p className="text-white font-heading font-bold text-lg">{lastResult.water_depth_m}m</p>
                </div>
                <div className="text-center">
                  <p className="text-slate-400 text-xs">Velocity</p>
                  <p className="text-white font-heading font-bold text-lg">{lastResult.water_velocity_ms} m/s</p>
                </div>
                <div className="text-center">
                  <p className="text-slate-400 text-xs">Confidence</p>
                  <p className="text-white font-heading font-bold text-lg">{(lastResult.confidence * 100).toFixed(0)}%</p>
                </div>
                <div className="text-center">
                  <p className="text-slate-400 text-xs">Area</p>
                  <p className="text-white font-heading font-bold text-lg">{lastResult.surface_area_m2?.toLocaleString()} m²</p>
                </div>
              </div>
              <div className={`text-center py-1.5 rounded-lg text-xs font-bold ${
                lastResult.alert_level === 'EMERGENCY' ? 'bg-red-600 text-white' :
                lastResult.alert_level === 'WARNING'   ? 'bg-yellow-500 text-black' :
                'bg-green-600 text-white'
              }`}>
                {lastResult.alert_level} | {lastResult.cv_method}
              </div>
            </div>
          )}

          {/* Recent gauge readings (from gateway aggregation) */}
          {gauges.length > 0 && (
            <div>
              <h3 className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
                Recent Gauge Readings
              </h3>
              <div className="space-y-1">
                {gauges.filter(g => g.source === 'DRONE' || g.source === 'VIRTUAL').slice(0, 4).map(g => (
                  <div key={g.station_id} className="flex items-center gap-3 px-3 py-2 bg-slate-800/60 rounded-lg text-sm">
                    <div className={`w-2 h-2 rounded-full ${
                      g.quality_flag === 'REAL' ? 'bg-green-400' : 'bg-yellow-400'
                    }`} />
                    <span className="text-slate-300 flex-1 truncate">{g.station_name}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-900 text-purple-300">
                      {g.source === 'DRONE' ? 'Drone' : 'PINN'}
                    </span>
                    <span className="font-mono font-bold text-white">{g.level_m?.toFixed(2)}m</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default DroneMapPanel
