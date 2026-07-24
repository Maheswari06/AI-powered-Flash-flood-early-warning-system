import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import API from '../config/api'

/**
 * ScarNetPanel — Satellite terrain change panel
 *
 * ┌───────────────────────────────────────────────┐
 * │  🛰️ ScarNet Terrain Intelligence              │
 * ├──────────────────────┬────────────────────────┤
 * │  Before / After      │  TerrainHealthBar      │
 * │  comparison slider   │  ChangeCards           │
 * │                      │  PINN Update Banner    │
 * └──────────────────────┴────────────────────────┘
 */

const CHANGE_ICONS = {
  DEFORESTATION: '🌲',
  SLOPE_FAILURE: '⛰️',
  URBANIZATION: '🏗️',
  RIVER_WIDENING: '🌊',
  EROSION: '💨',
  MINING: '⛏️',
}

const SEVERITY_COLORS = {
  LOW: '#22c55e',
  MEDIUM: '#f59e0b',
  HIGH: '#ef4444',
  CRITICAL: '#dc2626',
}

function TerrainHealthBar({ score }) {
  if (score == null) return null
  const pct = Math.round(score * 100)
  const color = pct > 80 ? '#22c55e' : pct > 60 ? '#f59e0b' : '#ef4444'

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-400 font-body uppercase tracking-wide">
          Terrain Health Score
        </span>
        <span className="font-code text-lg" style={{ color }}>{pct}%</span>
      </div>
      <div className="terrain-health-bar">
        <div className="marker" style={{ left: `${pct}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-gray-600 mt-1">
        <span>Critical</span>
        <span>Degraded</span>
        <span>Healthy</span>
      </div>
    </div>
  )
}

function ChangeCard({ change, index }) {
  const icon = CHANGE_ICONS[change.type] || '🔍'
  const severityColor = SEVERITY_COLORS[change.severity] || '#94a3b8'

  return (
    <div className={`glass-card p-3 animate-slide-up slide-delay-${index + 1}`}>
      <div className="flex items-start gap-2">
        <span className="text-lg">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-heading font-semibold text-white">
              {change.type.replace(/_/g, ' ')}
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-code"
              style={{
                color: severityColor,
                background: `${severityColor}15`,
                border: `1px solid ${severityColor}30`,
              }}
            >
              {change.severity}
            </span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-gray-400">
            <span>{change.area_ha} ha</span>
            <span className="text-gray-600">•</span>
            <span>{change.impact}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function PINNBanner({ visible, onDismiss }) {
  if (!visible) return null
  return (
    <div className="intervention-result animate-slide-up mt-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">🧠</span>
        <span className="text-xs font-heading font-bold text-accent">
          PINN Model Update Required
        </span>
      </div>
      <p className="text-[11px] text-gray-300 leading-relaxed">
        Terrain changes exceed the PINN recalibration threshold.
        The flood prediction model should be updated to incorporate new drainage
        patterns and land cover changes.
      </p>
      <button
        onClick={onDismiss}
        className="mt-2 text-[10px] text-gray-500 hover:text-accent transition-colors"
      >
        Acknowledged
      </button>
    </div>
  )
}

function ComparisonSlider({ beforeDate, afterDate }) {
  const [sliderPos, setSliderPos] = useState(50)
  const containerRef = useRef(null)
  const dragging = useRef(false)

  const handleMove = useCallback((clientX) => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
    setSliderPos(pct)
  }, [])

  const onMouseDown = () => { dragging.current = true }
  const onMouseUp = () => { dragging.current = false }
  const onMouseMove = useCallback((e) => {
    if (dragging.current) handleMove(e.clientX)
  }, [handleMove])

  useEffect(() => {
    window.addEventListener('mouseup', onMouseUp)
    window.addEventListener('mousemove', onMouseMove)
    return () => {
      window.removeEventListener('mouseup', onMouseUp)
      window.removeEventListener('mousemove', onMouseMove)
    }
  }, [onMouseMove])

  // Simulated satellite imagery with NDVI-style gradient maps
  return (
    <div
      ref={containerRef}
      className="comparison-slider aspect-[16/10] bg-navy-mid"
      style={{
        '--slider-pos': `${sliderPos}%`,
        '--clip-right': `${100 - sliderPos}%`,
      }}
      onMouseDown={onMouseDown}
    >
      {/* Before — green healthy terrain */}
      <div
        className="before-img"
        style={{
          background: `
            radial-gradient(ellipse at 30% 50%, #1a4a2c 0%, transparent 60%),
            radial-gradient(ellipse at 70% 40%, #1e5c34 0%, transparent 50%),
            radial-gradient(ellipse at 50% 70%, #245a35 0%, transparent 55%),
            linear-gradient(135deg, #0d2818 0%, #1a4028 30%, #1e5030 50%, #163a22 100%)
          `,
          clipPath: `inset(0 ${100 - sliderPos}% 0 0)`,
        }}
      >
        <div className="absolute bottom-2 left-2 bg-black/60 px-2 py-1 rounded text-[10px] text-green-400 font-code z-20">
          BEFORE — {beforeDate || '2022-08-15'}
        </div>
      </div>

      {/* After — degraded terrain with red patches */}
      <div
        className="after-img"
        style={{
          background: `
            radial-gradient(ellipse at 25% 45%, #4a2a1a 0%, transparent 40%),
            radial-gradient(ellipse at 60% 35%, #5c3a1e 0%, transparent 35%),
            radial-gradient(ellipse at 45% 65%, #3a201a 0%, transparent 30%),
            radial-gradient(ellipse at 75% 55%, #5a3020 0%, transparent 25%),
            linear-gradient(135deg, #1a2818 0%, #2a3020 30%, #3a2820 50%, #2a2018 100%)
          `,
        }}
      >
        <div className="absolute bottom-2 right-2 bg-black/60 px-2 py-1 rounded text-[10px] text-red-400 font-code z-20">
          AFTER — {afterDate || '2023-09-15'}
        </div>
      </div>

      {/* Slider handle */}
      <div className="slider-handle">
        <div className="slider-knob">◀▶</div>
      </div>

      {/* Overlay labels */}
      <div className="absolute top-2 left-1/2 -translate-x-1/2 bg-black/70 px-3 py-1 rounded-full text-[10px] text-gray-300 font-code z-20">
        Beas Valley, Himachal Pradesh
      </div>
    </div>
  )
}

export default function ScarNetPanel({ demoMode = false, fullScreen = false }) {
  const [scan, setScan] = useState(null)
  const [beforeMeta, setBeforeMeta] = useState(null)
  const [afterMeta, setAfterMeta] = useState(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [pinnAcked, setPinnAcked] = useState(false)
  const [error, setError] = useState(null)

  const fetchLatest = useCallback(async () => {
    try {
      const [scanRes, beforeRes, afterRes] = await Promise.all([
        axios.get(API.scarnetLatest),
        axios.get(API.scarnetTiles.before),
        axios.get(API.scarnetTiles.after),
      ])
      setScan(scanRes.data)
      setBeforeMeta(beforeRes.data)
      setAfterMeta(afterRes.data)
      setError(null)
    } catch (err) {
      // Use demo data on failure
      setScan({
        status: 'ok',
        terrain_health_score: 0.861,
        total_area_changed_ha: 145.8,
        pinn_update_required: true,
        scan_duration_ms: 1247,
        summary: 'Detected 2 terrain changes in Beas Valley catchment',
        changes: [
          { type: 'DEFORESTATION', area_hectares: 111.8, severity: 'HIGH', flood_risk_impact: 'Increases runoff coefficient by 35%' },
          { type: 'SLOPE_FAILURE', area_hectares: 34.0, severity: 'MEDIUM', flood_risk_impact: 'Debris flow risk in downstream channel' },
        ],
      })
      setBeforeMeta({ date: '2022-08-15', location: 'Beas Valley, Himachal Pradesh' })
      setAfterMeta({ date: '2023-09-15', location: 'Beas Valley, Himachal Pradesh' })
      setError(null) // Silently fall back to demo
    } finally {
      setLoading(false)
    }
  }, [])

  const triggerScan = async () => {
    setScanning(true)
    setPinnAcked(false)
    try {
      const res = await axios.post(API.scarnetTrigger)
      setScan({ status: 'ok', ...res.data })
    } catch {
      // Keep current data
    } finally {
      setScanning(false)
    }
  }

  useEffect(() => { fetchLatest() }, [fetchLatest])

  // Normalize changes from scan result
  const changes = scan?.changes?.map(c => ({
    type: c.type || c.change_type,
    area_ha: c.area_ha ?? c.area_hectares ?? 0,
    severity: c.severity || 'MEDIUM',
    impact: c.impact || c.flood_risk_impact || '',
  })) || []

  if (loading) {
    return (
      <div className={`${fullScreen ? 'flex-1' : ''} flex items-center justify-center bg-navy min-h-[400px]`}>
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400 font-body text-sm">Loading ScarNet data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`${fullScreen ? 'flex-1' : ''} p-4 overflow-auto`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-xl">🛰️</span>
          <div>
            <h2 className="font-heading text-lg font-bold text-white">
              ScarNet Terrain Intelligence
            </h2>
            <p className="text-[11px] text-gray-500">
              Satellite change detection · PINN integration
            </p>
          </div>
        </div>
        <button
          onClick={triggerScan}
          disabled={scanning}
          className={`px-3 py-1.5 rounded-lg text-xs font-heading font-semibold transition-all ${
            scanning
              ? 'bg-gray-700 text-gray-400 cursor-wait'
              : 'bg-accent/10 text-accent border border-accent/30 hover:bg-accent/20'
          }`}
        >
          {scanning ? (
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
              Scanning...
            </span>
          ) : '🛰️ Trigger Demo Scan'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Left: Comparison slider (3 cols) */}
        <div className="lg:col-span-3 space-y-3">
          <ComparisonSlider
            beforeDate={beforeMeta?.date}
            afterDate={afterMeta?.date}
          />

          {/* Scan summary stats */}
          {scan?.status === 'ok' && (
            <div className="grid grid-cols-3 gap-2">
              <div className="glass-card p-3 text-center">
                <div className="font-code text-lg text-accent">
                  {changes.length}
                </div>
                <div className="text-[10px] text-gray-500 uppercase">Changes</div>
              </div>
              <div className="glass-card p-3 text-center">
                <div className="font-code text-lg text-amber-400">
                  {scan.total_area_changed_ha?.toFixed(1) ?? '—'} ha
                </div>
                <div className="text-[10px] text-gray-500 uppercase">Area Affected</div>
              </div>
              <div className="glass-card p-3 text-center">
                <div className="font-code text-lg text-gray-300">
                  {scan.scan_duration_ms ?? '—'} ms
                </div>
                <div className="text-[10px] text-gray-500 uppercase">Scan Time</div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Health + Changes (2 cols) */}
        <div className="lg:col-span-2 space-y-3">
          <TerrainHealthBar score={scan?.terrain_health_score} />

          {changes.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs text-gray-400 font-heading uppercase tracking-wide">
                Detected Changes
              </h3>
              {changes.map((c, i) => (
                <ChangeCard key={i} change={c} index={i} />
              ))}
            </div>
          )}

          <PINNBanner
            visible={scan?.pinn_update_required && !pinnAcked}
            onDismiss={() => setPinnAcked(true)}
          />

          {scan?.summary && (
            <div className="text-[11px] text-gray-500 font-body leading-relaxed mt-2">
              {scan.summary}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
