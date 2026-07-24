/**
 * MirrorPanel — Phase 2 Counterfactual "What if?" analysis dashboard.
 *
 * Two-column layout: actual vs counterfactual outcomes.
 * Features: intervention time slider, AnimatedCounter (lives saved),
 * 4 counterfactual result cards, PDF report download.
 */

import { useState, useEffect, useRef } from 'react'
import useMirrorData from '../hooks/useMirrorData'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts'

// AnimatedCounter — counts up from 0 to target with easing
function AnimatedCounter({ value, duration = 1500, className = '' }) {
  const [display, setDisplay] = useState(0)
  const ref = useRef(null)

  useEffect(() => {
    if (value == null) return
    let start = 0
    const startTime = performance.now()
    const animate = (now) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(eased * value))
      if (progress < 1) {
        ref.current = requestAnimationFrame(animate)
      }
    }
    ref.current = requestAnimationFrame(animate)
    return () => { if (ref.current) cancelAnimationFrame(ref.current) }
  }, [value, duration])

  return <span className={className}>{display}</span>
}

const CF_COLORS = {
  CF_001: { bg: 'bg-blue-900/30', border: 'border-blue-700', accent: 'text-blue-400', icon: '🌊' },
  CF_002: { bg: 'bg-orange-900/30', border: 'border-orange-700', accent: 'text-orange-400', icon: '🚨' },
  CF_003: { bg: 'bg-green-900/30', border: 'border-green-700', accent: 'text-green-400', icon: '📡' },
  CF_004: { bg: 'bg-emerald-900/30', border: 'border-emerald-700', accent: 'text-emerald-400', icon: '🌳' },
}

export default function MirrorPanel({ demoMode = false, fullScreen = false }) {
  const { event, counterfactuals, sliderData, loading, downloadReport } = useMirrorData(demoMode)
  const [expanded, setExpanded] = useState(true)
  const [sliderValue, setSliderValue] = useState(60)
  const [selectedCF, setSelectedCF] = useState(null)
  const [showTimeline, setShowTimeline] = useState(false)

  // Compute slider interpolation
  const sliderPoint = sliderData.find(d => d.time_before_peak_min === sliderValue) ||
    sliderData[Math.round(sliderValue / 5)] || {}

  // Compact overlay mode
  if (!fullScreen) {
    if (!expanded) {
      return (
        <button
          onClick={() => setExpanded(true)}
          className="bg-navy/90 border border-gray-700 text-purple-400 text-xs font-mono px-3 py-2 rounded-lg hover:border-purple-400 transition-colors"
        >
          MIRROR ▸
        </button>
      )
    }

    const bestCF = counterfactuals[0]
    return (
      <div className="bg-navy/95 backdrop-blur-sm border border-gray-700 rounded-xl p-4 max-w-xs">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-display text-sm text-white tracking-wider">
            <span className="text-purple-400">MIRROR</span>
          </h3>
          <button onClick={() => setExpanded(false)} className="text-gray-500 text-xs hover:text-white">✕</button>
        </div>
        {bestCF && (
          <div className="text-xs text-gray-400">
            Best: {bestCF.cf_label} — <span className="text-green-400">{bestCF.lives_saved_estimate} lives saved</span>
          </div>
        )}
      </div>
    )
  }

  // ── Full-screen mode ──────────────────────────────────────────────
  return (
    <div className="flex-1 flex flex-col bg-navy p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="font-display text-white tracking-wider text-lg">
            🔮 MIRROR — <span className="text-purple-400">Counterfactual Engine</span>
          </h2>
          {event && (
            <p className="text-xs text-gray-500 mt-1">
              {event.name} · {event.date} · {event.location}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowTimeline(!showTimeline)}
            className={`text-[10px] font-mono border rounded px-3 py-1.5 transition-colors ${
              showTimeline ? 'border-purple-500 text-purple-400 bg-purple-900/20' : 'border-gray-700 text-gray-400 hover:border-purple-500'
            }`}
          >
            📊 Timeline
          </button>
          <button
            onClick={downloadReport}
            className="text-[10px] font-mono text-gray-400 border border-gray-700 rounded px-3 py-1.5 hover:border-accent hover:text-accent transition-colors"
          >
            📄 PDF Report
          </button>
        </div>
      </div>

      {/* Two-column: Actual vs What-If */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Actual outcomes */}
        <div className="bg-red-900/10 border border-red-900/30 rounded-xl p-5">
          <h3 className="text-xs text-red-400 uppercase tracking-wider font-mono mb-4">
            ■ ACTUAL OUTCOME
          </h3>
          <div className="space-y-3">
            <div>
              <div className="text-4xl text-red-400 font-mono font-bold">
                {event?.lives_lost || 0}
              </div>
              <div className="text-[10px] text-gray-500 uppercase">Lives Lost</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-lg text-white font-mono">{event?.peak_flood_depth_m || 0}m</div>
                <div className="text-[9px] text-gray-500">Peak Depth</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">T{event?.official_warning_time_min || 0}min</div>
                <div className="text-[9px] text-gray-500">Warning Time</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">₹{event?.damage_crore_inr || 0} Cr</div>
                <div className="text-[9px] text-gray-500">Damage</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">{event?.affected_population?.toLocaleString() || 0}</div>
                <div className="text-[9px] text-gray-500">Affected</div>
              </div>
            </div>
          </div>
        </div>

        {/* Best counterfactual outcome */}
        <div className="bg-green-900/10 border border-green-900/30 rounded-xl p-5">
          <h3 className="text-xs text-green-400 uppercase tracking-wider font-mono mb-4">
            ■ BEST COUNTERFACTUAL — {counterfactuals[0]?.cf_label || '...'}
          </h3>
          <div className="space-y-3">
            <div>
              <AnimatedCounter
                value={counterfactuals[0]?.lives_saved_estimate || 0}
                className="text-6xl text-green-400 font-mono font-bold"
                duration={2000}
              />
              <div className="text-[10px] text-gray-500 uppercase">Lives Saved</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-lg text-white font-mono">{counterfactuals[0]?.peak_depth_m || 0}m</div>
                <div className="text-[9px] text-gray-500">Reduced Peak</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">T{counterfactuals[0]?.intervention_time_min || 0}min</div>
                <div className="text-[9px] text-gray-500">Intervention</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">₹{counterfactuals[0]?.damage_avoided_crore || 0} Cr</div>
                <div className="text-[9px] text-gray-500">Damage Avoided</div>
              </div>
              <div>
                <div className="text-lg text-white font-mono">{counterfactuals[0]?.confidence ? `${(counterfactuals[0].confidence * 100).toFixed(0)}%` : '—'}</div>
                <div className="text-[9px] text-gray-500">Confidence</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Intervention Time Slider */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-xl p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs text-purple-400 uppercase tracking-wider font-mono">
            Intervention Time Slider
          </h3>
          <div className="text-xs text-gray-400 font-mono">
            T-{sliderValue} min before peak
          </div>
        </div>

        <input
          type="range"
          min="0"
          max="180"
          step="5"
          value={sliderValue}
          onChange={(e) => setSliderValue(parseInt(e.target.value))}
          className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
        />

        <div className="flex justify-between text-[9px] text-gray-600 mt-1">
          <span>T-0 (peak)</span>
          <span>T-45</span>
          <span>T-90</span>
          <span>T-135</span>
          <span>T-180</span>
        </div>

        {/* Slider results */}
        <div className="grid grid-cols-3 gap-4 mt-4">
          <div className="text-center">
            <AnimatedCounter
              value={sliderPoint.lives_saved_estimate || 0}
              className="text-3xl text-green-400 font-mono font-bold"
            />
            <div className="text-[9px] text-gray-500 uppercase mt-1">Lives Saved</div>
          </div>
          <div className="text-center">
            <div className="text-3xl text-cyan-400 font-mono font-bold">
              {sliderPoint.peak_depth_m || '—'}m
            </div>
            <div className="text-[9px] text-gray-500 uppercase mt-1">Peak Depth</div>
          </div>
          <div className="text-center">
            <div className="text-3xl text-amber-400 font-mono font-bold">
              {sliderPoint.damage_reduction_pct || 0}%
            </div>
            <div className="text-[9px] text-gray-500 uppercase mt-1">Damage Reduced</div>
          </div>
        </div>
      </div>

      {/* Slider Chart (optional) */}
      {showTimeline && sliderData.length > 0 && (
        <div className="bg-gray-800/30 border border-gray-700 rounded-xl p-5 mb-6">
          <h3 className="text-xs text-purple-400 uppercase tracking-wider font-mono mb-3">
            Intervention Impact Curve
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={sliderData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis
                dataKey="time_before_peak_min"
                reversed
                tick={{ fontSize: 9, fill: '#666' }}
                label={{ value: 'Minutes before peak', position: 'insideBottomRight', fontSize: 9, fill: '#555' }}
              />
              <YAxis
                yAxisId="lives"
                tick={{ fontSize: 9, fill: '#666' }}
                width={35}
                label={{ value: 'Lives', angle: -90, position: 'insideLeft', fontSize: 9, fill: '#666' }}
              />
              <YAxis
                yAxisId="depth"
                orientation="right"
                tick={{ fontSize: 9, fill: '#666' }}
                width={35}
                label={{ value: 'Depth (m)', angle: 90, position: 'insideRight', fontSize: 9, fill: '#666' }}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333', fontSize: 10 }}
                labelFormatter={(v) => `T-${v} min`}
              />
              <ReferenceLine x={sliderValue} yAxisId="lives" stroke="#a855f7" strokeDasharray="3 3" />
              <Line yAxisId="lives" type="monotone" dataKey="lives_saved_estimate" stroke="#22c55e" strokeWidth={2} dot={false} name="Lives Saved" />
              <Line yAxisId="depth" type="monotone" dataKey="peak_depth_m" stroke="#ef4444" strokeWidth={2} dot={false} name="Peak Depth (m)" />
              <Legend wrapperStyle={{ fontSize: 9 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Counterfactual Cards */}
      <div className="grid grid-cols-2 gap-4">
        {counterfactuals.map((cf) => {
          const style = CF_COLORS[cf.cf_id] || { bg: 'bg-gray-800/30', border: 'border-gray-700', accent: 'text-gray-400', icon: '🔮' }
          const isSelected = selectedCF === cf.cf_id
          return (
            <div
              key={cf.cf_id}
              onClick={() => setSelectedCF(isSelected ? null : cf.cf_id)}
              className={`${style.bg} border ${style.border} rounded-xl p-4 cursor-pointer transition-all ${
                isSelected ? 'ring-1 ring-purple-500/50 shadow-lg' : 'hover:shadow-md'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{style.icon}</span>
                  <span className={`text-sm font-display ${style.accent}`}>{cf.cf_label}</span>
                </div>
                <span className="text-[9px] font-mono text-gray-500">
                  {cf.confidence ? `${(cf.confidence * 100).toFixed(0)}%` : ''} conf.
                </span>
              </div>

              <div className="text-xs text-gray-400 mb-3 line-clamp-2">{cf.description}</div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <div className="text-xl text-green-400 font-mono font-bold">{cf.lives_saved_estimate}</div>
                  <div className="text-[8px] text-gray-500 uppercase">Saved</div>
                </div>
                <div>
                  <div className="text-xl text-cyan-400 font-mono font-bold">{cf.peak_depth_m}m</div>
                  <div className="text-[8px] text-gray-500 uppercase">Peak</div>
                </div>
                <div>
                  <div className="text-xl text-amber-400 font-mono font-bold">₹{cf.damage_avoided_crore}</div>
                  <div className="text-[8px] text-gray-500 uppercase">Cr Saved</div>
                </div>
              </div>

              {isSelected && (
                <div className="mt-3 pt-3 border-t border-gray-700/50">
                  <div className="text-[10px] text-gray-500 uppercase mb-1">Interventions:</div>
                  {cf.intervention_actions?.map((a, i) => (
                    <div key={i} className="text-[9px] text-gray-400 flex gap-1 mb-0.5">
                      <span className={`${style.accent}`}>▸</span> {a}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {counterfactuals.length === 0 && !loading && (
        <div className="text-center py-12">
          <div className="text-5xl mb-3">🔮</div>
          <div className="text-sm text-gray-500">No counterfactual data loaded</div>
          <div className="text-[10px] text-gray-600 mt-1">Enable demo mode to see Himachal Pradesh 2023 analysis</div>
        </div>
      )}
    </div>
  )
}
