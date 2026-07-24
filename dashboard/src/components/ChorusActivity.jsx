/**
 * ChorusActivity — Phase 2 enhanced community intelligence dashboard.
 *
 * Full-screen: signal feed with classification/language/trust_weight,
 * village sentiment cards, consensus alerts, demo generation.
 */

import { useState } from 'react'
import useChorusSignals from '../hooks/useChorusSignals'

const SENTIMENT_BADGES = {
  CALM:      { bg: 'bg-green-900/40', border: 'border-green-700', text: 'text-green-400', icon: '😊', gradient: 'from-green-900/20' },
  CONCERNED: { bg: 'bg-yellow-900/40', border: 'border-yellow-700', text: 'text-yellow-400', icon: '😟', gradient: 'from-yellow-900/20' },
  ANXIOUS:   { bg: 'bg-orange-900/40', border: 'border-orange-700', text: 'text-orange-400', icon: '😰', gradient: 'from-orange-900/20' },
  PANIC:     { bg: 'bg-red-900/40', border: 'border-red-700', text: 'text-red-400', icon: '🚨', gradient: 'from-red-900/20' },
}

const CLASSIFICATION_COLORS = {
  FLOOD_WARNING: 'text-red-400',
  INFRASTRUCTURE_DAMAGE: 'text-orange-400',
  WEATHER_REPORT: 'text-blue-400',
  STATUS_UPDATE: 'text-green-400',
  RESCUE_REQUEST: 'text-red-500',
}

const LANGUAGE_FLAGS = {
  hi: '🇮🇳 Hindi',
  en: '🇬🇧 English',
  as: '🇮🇳 Assamese',
  bn: '🇮🇳 Bengali',
}

export default function ChorusActivity({ selectedVillage = null, demoMode = false, fullScreen = false }) {
  const { stats, signals, loading, generateDemo } = useChorusSignals(demoMode)
  const [expanded, setExpanded] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [selectedVillageFilter, setSelectedVillageFilter] = useState(null)

  const handleGenerate = async () => {
    setGenerating(true)
    await generateDemo(selectedVillage || 'kullu_01', 5)
    setTimeout(() => setGenerating(false), 1000)
  }

  // Compact overlay mode
  if (!fullScreen) {
    if (!expanded) {
      return (
        <button
          onClick={() => setExpanded(true)}
          className="bg-navy/90 border border-gray-700 text-emerald-400 text-xs font-mono px-3 py-2 rounded-lg hover:border-emerald-400 transition-colors"
        >
          CHORUS ▸
        </button>
      )
    }

    return (
      <div className="bg-navy/95 backdrop-blur-sm border border-gray-700 rounded-xl p-4 max-w-xs">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-display text-sm text-white tracking-wider">
            <span className="text-emerald-400">CHORUS</span>
          </h3>
          <button onClick={() => setExpanded(false)} className="text-gray-500 text-xs hover:text-white">✕</button>
        </div>
        <div className="text-xs text-gray-400">
          {stats?.total_reports || 0} reports · {stats?.villages_reporting || 0} villages
        </div>
      </div>
    )
  }

  // ── Full-screen mode ──────────────────────────────────────────────
  const aggregations = stats?.aggregations ? Object.values(stats.aggregations) : []
  aggregations.sort((a, b) => (b.panic_ratio || 0) - (a.panic_ratio || 0))

  const filteredSignals = selectedVillageFilter
    ? signals.filter(s => s.village_id === selectedVillageFilter)
    : signals

  return (
    <div className="flex-1 flex bg-navy">
      {/* Left panel — Village sentiment cards */}
      <div className="w-80 border-r border-gray-800 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-white tracking-wider text-sm">
              📢 <span className="text-emerald-400">CHORUS</span> · Community Intel
            </h2>
          </div>

          {/* Global stats */}
          <div className="grid grid-cols-3 gap-2 mb-3">
            <div className="bg-gray-800/40 rounded-lg p-2 text-center">
              <div className="text-xl text-white font-mono font-bold">{stats?.total_reports || 0}</div>
              <div className="text-[8px] text-gray-500 uppercase">Reports</div>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-2 text-center">
              <div className="text-xl text-emerald-400 font-mono font-bold">{stats?.villages_reporting || 0}</div>
              <div className="text-[8px] text-gray-500 uppercase">Villages</div>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-2 text-center">
              <div className={`text-xl font-mono font-bold ${stats?.consensus_active ? 'text-green-400' : 'text-gray-500'}`}>
                {stats?.consensus_active ? '✓' : '—'}
              </div>
              <div className="text-[8px] text-gray-500 uppercase">Consensus</div>
            </div>
          </div>

          {/* Demo generate */}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="w-full text-xs font-mono bg-emerald-900/20 text-emerald-400 border border-emerald-900/40 rounded-lg px-3 py-2 hover:bg-emerald-900/30 disabled:opacity-50 transition-colors"
          >
            {generating ? '⟳ GENERATING...' : '📝 GENERATE DEMO REPORTS'}
          </button>
        </div>

        {/* Village sentiment cards */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {aggregations.map((agg) => {
            const badge = SENTIMENT_BADGES[agg.dominant_sentiment] || SENTIMENT_BADGES.CALM
            const isActive = selectedVillageFilter === agg.village_id
            return (
              <div
                key={agg.village_id}
                onClick={() => setSelectedVillageFilter(isActive ? null : agg.village_id)}
                className={`${badge.bg} border ${badge.border} rounded-lg p-3 cursor-pointer transition-all ${
                  isActive ? 'ring-1 ring-emerald-500/50 shadow-lg' : 'hover:shadow-md'
                }`}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs text-white font-medium">{agg.village_id}</span>
                  <span className={`text-[10px] font-mono ${badge.text}`}>
                    {badge.icon} {agg.dominant_sentiment}
                  </span>
                </div>

                <div className="flex gap-3 text-[9px] text-gray-400 mb-1.5">
                  <span>{agg.report_count} reports</span>
                  <span>flood: {(agg.flood_mention_rate * 100).toFixed(0)}%</span>
                  <span>panic: {(agg.panic_ratio * 100).toFixed(0)}%</span>
                </div>

                {/* Credibility bar */}
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-gray-700/50 rounded-full h-1">
                    <div
                      className="h-1 rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${(agg.avg_credibility || 0) * 100}%` }}
                    />
                  </div>
                  <span className="text-[8px] text-gray-500">{((agg.avg_credibility || 0) * 100).toFixed(0)}% cred</span>
                </div>

                {agg.community_risk_boost > 0.05 && (
                  <div className="text-[9px] text-amber-400 mt-1.5">
                    ⚠ Risk boost: +{(agg.community_risk_boost * 100).toFixed(1)}%
                  </div>
                )}

                {agg.top_keywords?.length > 0 && (
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    {agg.top_keywords.slice(0, 4).map((kw) => (
                      <span key={kw} className="text-[8px] bg-gray-800/60 rounded px-1.5 py-0.5 text-gray-500">
                        {kw}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {aggregations.length === 0 && (
            <div className="text-center py-8">
              <div className="text-3xl mb-2">📢</div>
              <div className="text-xs text-gray-500">No community reports yet</div>
              <div className="text-[10px] text-gray-600 mt-1">Click "GENERATE DEMO REPORTS" above</div>
            </div>
          )}
        </div>
      </div>

      {/* Right panel — Signal feed */}
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-sm text-white font-display tracking-wider">
              Live Signal Feed
            </h3>
            {selectedVillageFilter && (
              <span className="text-[10px] bg-emerald-900/30 text-emerald-400 px-2 py-0.5 rounded-full">
                Filtered: {selectedVillageFilter}
                <button
                  onClick={() => setSelectedVillageFilter(null)}
                  className="ml-1 text-emerald-300 hover:text-white"
                >×</button>
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 text-[9px] text-gray-500">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {signals.length} signals
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {filteredSignals.map((signal) => {
            const classColor = CLASSIFICATION_COLORS[signal.classification] || 'text-gray-400'
            const langLabel = LANGUAGE_FLAGS[signal.language] || signal.language
            const badge = SENTIMENT_BADGES[signal.sentiment] || SENTIMENT_BADGES.CALM
            return (
              <div
                key={signal.id}
                className={`bg-gradient-to-r ${badge.gradient} to-transparent border ${badge.border} rounded-lg p-4`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-mono ${classColor}`}>
                      {signal.classification?.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[9px] text-gray-600">·</span>
                    <span className="text-[9px] text-gray-500">{langLabel}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] font-mono ${badge.text}`}>
                      {badge.icon} {signal.sentiment}
                    </span>
                    <span className="text-[9px] text-gray-600">
                      trust: {((signal.trust_weight || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <div className="text-xs text-gray-300 mb-2 leading-relaxed">
                  "{signal.text}"
                </div>

                <div className="flex items-center justify-between text-[9px] text-gray-500">
                  <span>📍 {signal.village_id}</span>
                  {signal.location && (
                    <span>{signal.location.lat?.toFixed(2)}, {signal.location.lng?.toFixed(2)}</span>
                  )}
                  <span>{signal.timestamp ? new Date(signal.timestamp).toLocaleTimeString() : ''}</span>
                </div>

                {/* Trust weight bar */}
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex-1 bg-gray-700/30 rounded-full h-1">
                    <div
                      className={`h-1 rounded-full transition-all ${
                        signal.trust_weight > 0.7 ? 'bg-green-500' :
                        signal.trust_weight > 0.4 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${(signal.trust_weight || 0) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            )
          })}

          {filteredSignals.length === 0 && (
            <div className="text-center py-12">
              <div className="text-5xl mb-3">📡</div>
              <div className="text-sm text-gray-500">No signals received</div>
              <div className="text-[10px] text-gray-600 mt-1">
                {selectedVillageFilter
                  ? `No signals from ${selectedVillageFilter}`
                  : 'Enable demo mode or wait for community reports'}
              </div>
            </div>
          )}
        </div>

        {/* Consensus alert bar */}
        {aggregations.some(a => a.panic_ratio > 0.3) && (
          <div className="border-t border-red-900/50 bg-red-900/10 px-4 py-2 flex items-center gap-3">
            <span className="text-red-400 animate-pulse">🚨</span>
            <div className="flex-1">
              <div className="text-xs text-red-400 font-mono font-bold">CONSENSUS ALERT</div>
              <div className="text-[10px] text-red-300">
                High panic ratio detected in {aggregations.filter(a => a.panic_ratio > 0.3).map(a => a.village_id).join(', ')}
              </div>
            </div>
            <span className="text-[9px] text-gray-500 font-mono">
              {new Date().toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
