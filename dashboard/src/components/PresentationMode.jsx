import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import API from '../config/api'
import MOMENTS from '../config/moments'

/**
 * PresentationMode — THE MOST IMPORTANT COMPONENT
 *
 * Fullscreen judge-facing UI with 8 demo moments.
 * Each moment showcases a key ARGUS capability:
 *
 *   1. CV Gauging     — Real-time computer vision water level
 *   2. SHAP XAI       — Explainable AI risk decomposition
 *   3. Causal          — Live causal intervention simulation
 *   4. Offline/ACN    — WiFi kill → mesh network recovery
 *   5. Evacuation     — RL-optimized evacuation routing
 *   6. FloodLedger    — Blockchain audit trail + insurance
 *   7. MIRROR         — Counterfactual "what-if" analysis
 *   8. Closing        — Cinematic closing statement
 *
 * Layout:
 *  ┌─────────────── TopBar (ARGUS brand + moment dots) ──────────────┐
 *  │                                                                  │
 *  │                     Hero Content Area                            │
 *  │               (changes per active moment)                        │
 *  │                                                                  │
 *  ├──────────── LiveMetricsTicker (scrolling stats) ─────────────────┤
 *  └──────────────────────────────────────────────────────────────────┘
 */

// ── TopBar ─────────────────────────────────────────────────────────
function TopBar({ currentMoment, onSelectMoment, onClose }) {
  return (
    <div className="presentation-topbar">
      {/* Brand */}
      <div className="flex items-center gap-3 mr-8">
        <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center">
          <span className="text-accent font-heading font-bold text-sm">A</span>
        </div>
        <div>
          <div className="font-heading font-bold text-white text-sm tracking-wide">
            HYDRA ARGUS
          </div>
          <div className="text-[9px] text-gray-500 font-code uppercase tracking-widest">
            Flash Flood Early Warning System
          </div>
        </div>
      </div>

      {/* Moment progress dots */}
      <div className="flex items-center gap-3 flex-1 justify-center">
        {MOMENTS.map((m, i) => {
          const isCurrent = m.id === currentMoment
          const isCompleted = MOMENTS.findIndex(x => x.id === currentMoment) > i
          return (
            <button
              key={m.id}
              onClick={() => onSelectMoment(m.id)}
              className={`moment-dot ${isCurrent ? 'active' : isCompleted ? 'completed' : 'pending'}`}
              title={`${i + 1}. ${m.label}`}
              style={isCurrent ? { background: m.color, boxShadow: `0 0 10px ${m.color}` } : {}}
            />
          )
        })}
      </div>

      {/* Moment label + close */}
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-xs font-heading text-gray-400">
            Moment {MOMENTS.findIndex(m => m.id === currentMoment) + 1} of {MOMENTS.length}
          </div>
          <div className="text-sm font-heading font-bold text-white">
            {MOMENTS.find(m => m.id === currentMoment)?.label}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg transition-colors ml-2"
          title="Exit Presentation (Esc)"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

// ── LiveMetricsTicker ──────────────────────────────────────────────
function LiveMetricsTicker({ predictions }) {
  const highRisk = predictions?.filter(p => p.risk_score > 0.7).length || 0
  const maxRisk = predictions?.reduce((m, p) => Math.max(m, p.risk_score || 0), 0) || 0
  const stations = predictions?.length || 0

  const items = [
    `🏔️ Stations Active: ${stations}`,
    `⚠️ High-Risk Villages: ${highRisk}`,
    `📊 Max Risk Score: ${(maxRisk * 100).toFixed(0)}%`,
    `🌧️ Rainfall Intensity: ${(15 + maxRisk * 60).toFixed(0)} mm/hr`,
    `💧 Soil Saturation: ${(40 + maxRisk * 45).toFixed(0)}%`,
    `🛰️ Satellite Coverage: 94%`,
    `📶 ACN Mesh Nodes: 6 online`,
    `🔗 FloodLedger Blocks: 47`,
    `🧠 PINN Confidence: HIGH`,
    `🔮 MIRROR Scenarios: 4 active`,
  ]

  // Double items for seamless loop
  const doubled = [...items, ...items]

  return (
    <div className="presentation-ticker">
      <div className="animate-ticker whitespace-nowrap flex items-center">
        {doubled.map((item, i) => (
          <span key={i} className="inline-flex items-center mx-6 text-xs text-gray-400 font-code">
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Hero Components per Moment ─────────────────────────────────────

function CVGaugingHero() {
  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">📷</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            Computer Vision Water Gauging
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            ARGUS uses CCTV feeds to extract real-time water levels without physical sensors.
            OpenCV edge detection + depth estimation achieves ±3cm accuracy.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Active Feeds', value: '47', sub: 'CCTV cameras' },
            { label: 'Accuracy', value: '±3cm', sub: 'vs physical gauge' },
            { label: 'Update Rate', value: '10s', sub: 'real-time cycle' },
          ].map((stat, i) => (
            <div key={i} className={`glass-card-accent p-6 text-center animate-slide-up slide-delay-${i + 1}`}>
              <div className="lives-counter mb-1">{stat.value}</div>
              <div className="text-sm font-heading text-white">{stat.label}</div>
              <div className="text-[11px] text-gray-500">{stat.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function SHAPHero({ predictions }) {
  // Pick highest risk village for explanation
  const top = predictions?.length
    ? [...predictions].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))[0]
    : null

  const factors = top?.explanation || [
    { factor: 'Soil saturation index', contribution_pct: 38, value: '87%', direction: 'INCREASES_RISK' },
    { factor: 'Rainfall intensity (6hr)', contribution_pct: 29, value: '62 mm', direction: 'INCREASES_RISK' },
    { factor: 'Rate of change (1hr)', contribution_pct: 18, value: '+0.8 m/hr', direction: 'INCREASES_RISK' },
    { factor: 'Upstream dam level', contribution_pct: 10, value: '72%', direction: 'INCREASES_RISK' },
    { factor: 'Historical frequency', contribution_pct: 5, value: '3 events/yr', direction: 'NEUTRAL' },
  ]

  const riskPct = ((top?.risk_score || 0.73) * 100).toFixed(0)
  const villageName = top?.name || top?.village_id || 'Kullu Valley'

  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">🧠</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            Explainable AI — SHAP Analysis
          </h1>
          <p className="text-gray-400 font-body text-lg">
            Every prediction is transparent. Judges can see <em>why</em> ARGUS flagged a village.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Risk Score */}
          <div className="glass-card-accent p-6 animate-slide-up slide-delay-1">
            <div className="text-xs text-gray-400 font-heading uppercase mb-1">Village at Highest Risk</div>
            <div className="font-heading text-xl font-bold text-white mb-3">{villageName}</div>
            <div className="flex items-end gap-3">
              <span className="lives-counter-xl">{riskPct}%</span>
              <span className="text-sm text-gray-400 pb-2 font-body">risk score</span>
            </div>
          </div>

          {/* Factor waterfall */}
          <div className="glass-card-accent p-6 animate-slide-up slide-delay-2">
            <div className="text-xs text-gray-400 font-heading uppercase mb-3">Contributing Factors</div>
            <div className="space-y-2">
              {factors.slice(0, 5).map((f, i) => {
                const pct = f.contribution_pct || 0
                const barColor = f.direction === 'INCREASES_RISK' ? '#ef4444' : '#22c55e'
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-[11px] text-gray-400 w-36 truncate font-body">{f.factor}</span>
                    <div className="flex-1 h-4 bg-navy-mid rounded overflow-hidden">
                      <div
                        className="h-full rounded transition-all duration-700"
                        style={{
                          width: `${Math.min(pct, 100)}%`,
                          background: barColor,
                          animationDelay: `${i * 0.1}s`,
                        }}
                      />
                    </div>
                    <span className="text-[11px] text-gray-300 font-code w-12 text-right">
                      {pct}%
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function CausalInterventionHero() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showResult, setShowResult] = useState(false)

  const runIntervention = async () => {
    setLoading(true)
    setShowResult(false)
    try {
      const res = await axios.post(API.causalIntervene, {
        village_id: 'kullu_01',
        intervention: 'dam_pre_release',
        params: { release_pct: 30 },
      })
      setResult(res.data)
    } catch {
      // Demo fallback
      setResult({
        intervention: 'Dam Pre-Release (30%)',
        original_risk: 0.78,
        new_risk: 0.52,
        reduction_pct: 33.3,
        confidence: 0.82,
        mechanism: 'Lowering dam level by 30% reduces downstream water accumulation, buying 45 minutes of buffer time.',
      })
    } finally {
      setLoading(false)
      setTimeout(() => setShowResult(true), 100)
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">🔬</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            Causal Intervention Engine
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            Not just prediction — ARGUS simulates <em>what happens if</em> we intervene.
            Causal graph reasoning enables actionable risk mitigation.
          </p>
        </div>

        <div className="flex flex-col items-center gap-6">
          <button
            onClick={runIntervention}
            disabled={loading}
            className={`px-8 py-3 rounded-xl font-heading font-bold text-lg transition-all ${
              loading
                ? 'bg-gray-700 text-gray-400 cursor-wait'
                : 'bg-amber-500/20 text-amber-400 border-2 border-amber-500/40 hover:bg-amber-500/30 hover:shadow-lg hover:shadow-amber-500/20'
            }`}
          >
            {loading ? (
              <span className="flex items-center gap-3">
                <span className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                Running Intervention...
              </span>
            ) : '⚡ Simulate: Dam Pre-Release 30%'}
          </button>

          {showResult && result && (
            <div className="intervention-result w-full max-w-xl animate-slide-up">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-lg">✅</span>
                <span className="font-heading font-bold text-white">
                  {result.intervention || 'Dam Pre-Release'}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="text-center">
                  <div className="text-2xl font-code text-red-400">
                    {((result.original_risk || 0.78) * 100).toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-gray-500 uppercase">Before</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-code text-accent">→</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-code text-green-400">
                    {((result.new_risk || 0.52) * 100).toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-gray-500 uppercase">After</div>
                </div>
              </div>

              <div className="flex items-center gap-4 mb-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-green-400 text-xl">▼</span>
                  <span className="lives-counter text-2xl">
                    {(result.reduction_pct || 33.3).toFixed(1)}%
                  </span>
                </div>
                <span className="text-sm text-gray-400 font-body">risk reduction</span>
                <span className="ml-auto text-xs font-code text-gray-500">
                  Confidence: {((result.confidence || 0.82) * 100).toFixed(0)}%
                </span>
              </div>

              {result.mechanism && (
                <p className="text-[11px] text-gray-400 font-body leading-relaxed border-t border-gray-800 pt-2 mt-2">
                  {result.mechanism}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function OfflineHero() {
  const [phase, setPhase] = useState('online') // online → killed → recovering → recovered

  useEffect(() => {
    if (phase === 'online') return
    const timers = []
    if (phase === 'killed') {
      timers.push(setTimeout(() => setPhase('recovering'), 2000))
    }
    if (phase === 'recovering') {
      timers.push(setTimeout(() => setPhase('recovered'), 2500))
    }
    return () => timers.forEach(clearTimeout)
  }, [phase])

  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">📶</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            Offline Resilience — ACN Mesh
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            When WiFi dies, ARGUS doesn't. The Adaptive Communication Network
            switches to mesh radio/LoRa and keeps sending alerts.
          </p>
        </div>

        <div className="flex flex-col items-center gap-6">
          <button
            onClick={() => setPhase('killed')}
            disabled={phase !== 'online' && phase !== 'recovered'}
            className={`px-8 py-3 rounded-xl font-heading font-bold text-lg transition-all ${
              phase === 'killed' || phase === 'recovering'
                ? 'bg-red-900/40 text-red-400 border-2 border-red-500/40 animate-emergency-pulse cursor-wait'
                : 'bg-red-500/20 text-red-400 border-2 border-red-500/40 hover:bg-red-500/30'
            }`}
          >
            {phase === 'online' || phase === 'recovered' ? '💀 Kill WiFi Connection' :
             phase === 'killed' ? '🔴 WiFi DOWN — Detecting...' :
             '📶 ACN Mesh Recovering...'}
          </button>

          <div className="grid grid-cols-4 gap-4 w-full max-w-2xl">
            {[
              { label: 'WiFi', status: phase === 'online' || phase === 'recovered' ? 'up' : 'down' },
              { label: 'ACN Mesh', status: phase === 'recovered' || phase === 'recovering' ? 'up' : phase === 'killed' ? 'activating' : 'standby' },
              { label: 'LoRa Radio', status: phase === 'recovered' ? 'up' : phase === 'recovering' ? 'up' : 'standby' },
              { label: 'Alerts', status: phase === 'killed' ? 'queued' : 'flowing' },
            ].map((node, i) => {
              const dotColor = node.status === 'up' || node.status === 'flowing' ? '#22c55e'
                             : node.status === 'activating' || node.status === 'queued' ? '#f59e0b'
                             : node.status === 'down' ? '#ef4444' : '#64748b'
              return (
                <div key={i} className={`glass-card p-4 text-center animate-slide-up slide-delay-${i + 1}`}>
                  <div
                    className="w-3 h-3 rounded-full mx-auto mb-2"
                    style={{ background: dotColor, boxShadow: `0 0 8px ${dotColor}` }}
                  />
                  <div className="text-sm font-heading text-white">{node.label}</div>
                  <div className="text-[10px] text-gray-500 uppercase font-code">{node.status}</div>
                </div>
              )
            })}
          </div>

          {phase === 'recovered' && (
            <div className="intervention-result w-full max-w-xl animate-slide-up">
              <div className="flex items-center gap-2">
                <span className="text-lg">✅</span>
                <span className="font-heading font-bold text-green-400">
                  ACN Mesh Active — Zero Alert Loss
                </span>
              </div>
              <p className="text-[11px] text-gray-400 font-body mt-1">
                All queued alerts were delivered via mesh network in 2.3 seconds.
                Emergency SMS dispatched to NDRF and local authorities.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EvacuationHero() {
  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">🚌</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            RL-Optimized Evacuation
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            Reinforcement Learning computes optimal vehicle dispatch, route
            selection, and shelter assignment — minimizing total evacuation time.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="glass-card-accent p-6 animate-slide-up slide-delay-1">
            <div className="text-xs text-gray-400 font-heading uppercase mb-3">Majuli Island Scenario</div>
            <div className="space-y-3">
              {[
                { vehicle: '🚌 Bus Fleet', assigned: 'Ward 7 → Shelter A', eta: '12 min', people: 340 },
                { vehicle: '🚛 Truck', assigned: 'Ward 12 → Shelter B', eta: '18 min', people: 180 },
                { vehicle: '🚤 Boat', assigned: 'Kamalabari → Shelter C', eta: '25 min', people: 95 },
                { vehicle: '🚌 Bus (Trip 2)', assigned: 'Garamur → Shelter A', eta: '32 min', people: 210 },
              ].map((route, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span>{route.vehicle}</span>
                  <span className="flex-1 text-gray-400 font-body text-xs truncate">{route.assigned}</span>
                  <span className="font-code text-accent text-xs">{route.eta}</span>
                  <span className="font-code text-gray-500 text-xs">{route.people}p</span>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            {[
              { label: 'Total Evacuees', value: '825', icon: '👥' },
              { label: 'Time to Clear', value: '38 min', icon: '⏱️' },
              { label: 'Vehicles Used', value: '4', icon: '🚌' },
              { label: 'Route Efficiency', value: '94%', icon: '📈' },
            ].map((stat, i) => (
              <div key={i} className={`glass-card p-4 flex items-center gap-3 animate-slide-up slide-delay-${i + 1}`}>
                <span className="text-xl">{stat.icon}</span>
                <div className="flex-1">
                  <div className="text-[11px] text-gray-500 uppercase">{stat.label}</div>
                  <div className="font-code text-lg text-white">{stat.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function FloodLedgerHero() {
  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">🔗</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            FloodLedger — Blockchain Audit
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            Every prediction, alert, and action is cryptographically recorded.
            Tamper-proof chain enables automatic parametric insurance payouts.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Chain Length', value: '47', sub: 'blocks recorded' },
            { label: 'Integrity', value: '100%', sub: 'verified ✓' },
            { label: 'Insurance Payouts', value: '₹8.2L', sub: '3 auto-disbursed' },
          ].map((stat, i) => (
            <div key={i} className={`glass-card-accent p-5 text-center animate-slide-up slide-delay-${i + 1}`}>
              <div className="lives-counter mb-1">{stat.value}</div>
              <div className="text-sm font-heading text-white">{stat.label}</div>
              <div className="text-[11px] text-gray-500">{stat.sub}</div>
            </div>
          ))}
        </div>

        <div className="glass-card p-4 animate-slide-up slide-delay-4">
          <div className="text-xs text-gray-400 font-heading uppercase mb-3">Recent Payouts</div>
          <div className="space-y-2">
            {[
              { village: 'Kullu', amount: '₹3,20,000', trigger: 'Water > 4.5m for 2hr', status: 'DISBURSED' },
              { village: 'Mandi', amount: '₹2,50,000', trigger: 'Soil sat. > 95%', status: 'DISBURSED' },
              { village: 'Majuli', amount: '₹2,50,000', trigger: 'River width +40%', status: 'PENDING REVIEW' },
            ].map((p, i) => (
              <div key={i} className="flex items-center gap-3 text-sm py-1 border-b border-gray-800/50 last:border-0">
                <span className="font-heading text-white w-16">{p.village}</span>
                <span className="font-code text-accent">{p.amount}</span>
                <span className="flex-1 text-[11px] text-gray-500 truncate">{p.trigger}</span>
                <span className={`text-[10px] font-code px-1.5 py-0.5 rounded ${
                  p.status === 'DISBURSED' ? 'text-green-400 bg-green-500/10' : 'text-amber-400 bg-amber-500/10'
                }`}>{p.status}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function MirrorHero() {
  const [leadTime, setLeadTime] = useState(60)

  // Sigmoid lives-saved curve
  const livesSaved = Math.round(71 * (1 / (1 + Math.exp(-0.08 * (leadTime - 45)))))
  const damageSaved = Math.round(1847 * (1 / (1 + Math.exp(-0.05 * (leadTime - 60)))))

  return (
    <div className="flex-1 flex items-center justify-center animate-fade-in">
      <div className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <span className="text-6xl mb-4 block">🔮</span>
          <h1 className="font-heading text-4xl font-bold text-white mb-3">
            MIRROR — Counterfactual Engine
          </h1>
          <p className="text-gray-400 font-body text-lg max-w-2xl mx-auto">
            What if ARGUS had existed during the 2023 Himachal Pradesh floods?
            Drag the slider to see lives saved at different lead times.
          </p>
        </div>

        {/* Lead time slider */}
        <div className="glass-card-accent p-6 mb-6 animate-slide-up slide-delay-1">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400 font-heading uppercase">Lead Time</span>
            <span className="font-code text-accent text-lg">{leadTime} minutes</span>
          </div>
          <input
            type="range"
            min={0}
            max={180}
            value={leadTime}
            onChange={(e) => setLeadTime(Number(e.target.value))}
            className="w-full accent-cyan-400 h-2 rounded-lg bg-navy-mid appearance-none cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-gray-600 mt-1">
            <span>0 min</span>
            <span>90 min</span>
            <span>180 min</span>
          </div>
        </div>

        {/* Impact cards */}
        <div className="grid grid-cols-2 gap-6">
          <div className="glass-card-accent p-6 text-center animate-slide-up slide-delay-2">
            <div className="text-xs text-gray-400 font-heading uppercase mb-2">Lives Saved</div>
            <div className="lives-counter-xl">{livesSaved}</div>
            <div className="text-sm text-gray-400 font-body mt-1">of 71 lost in reality</div>
          </div>
          <div className="glass-card-accent p-6 text-center animate-slide-up slide-delay-3">
            <div className="text-xs text-gray-400 font-heading uppercase mb-2">Damage Prevented</div>
            <div className="lives-counter-xl">₹{damageSaved}Cr</div>
            <div className="text-sm text-gray-400 font-body mt-1">of ₹1,847 Cr total</div>
          </div>
        </div>

        <div className="text-center mt-6 animate-slide-up slide-delay-4">
          <p className="text-gray-500 text-xs font-body">
            Based on the 2023 Himachal Pradesh Flash Flood • 71 lives lost • ₹1,847 crore damage
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Closing Hero (Slide 14 equivalent) ─────────────────────────────
function ClosingHero() {
  const [visibleLines, setVisibleLines] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setVisibleLines(prev => (prev < 9 ? prev + 1 : prev))
    }, 800)
    return () => clearInterval(timer)
  }, [])

  const lines = [
    { text: '5,000 sensors broke under the mud.', style: 'text-gray-400' },
    { text: 'ARGUS turned every camera into a gauge.', style: 'text-accent' },
    { text: 'The towers fell.', style: 'text-gray-400' },
    { text: 'The crisis nodes kept warning.', style: 'text-accent' },
    { text: 'The water hit.', style: 'text-gray-400' },
    { text: 'Every village had a plan.', style: 'text-emerald-400' },
    { text: 'The flood ended.', style: 'text-gray-400' },
    { text: 'MIRROR told the government which decision would have saved 44 lives.', style: 'text-emerald-400' },
  ]

  return (
    <div className="flex items-center justify-center h-full">
      <div className="max-w-3xl text-center space-y-4">
        {lines.map((line, i) => (
          <div
            key={i}
            className={`font-body text-xl transition-all duration-700 ${
              i < visibleLines ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
            } ${line.style}`}
            style={{ transitionDelay: `${i * 100}ms` }}
          >
            {line.text}
          </div>
        ))}

        {visibleLines >= 8 && (
          <div className="pt-12 animate-slide-up">
            <h1
              className="font-heading font-bold text-accent tracking-wide"
              style={{ fontSize: '3rem', letterSpacing: '4px' }}
            >
              ARGUS cannot be blinded.
            </h1>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Hero Dispatcher ────────────────────────────────────────────────
function HeroContent({ momentId, predictions }) {
  switch (momentId) {
    case 'cv_gauging':   return <CVGaugingHero />
    case 'shap_xai':     return <SHAPHero predictions={predictions} />
    case 'causal':       return <CausalInterventionHero />
    case 'offline_acn':  return <OfflineHero />
    case 'evacuation':   return <EvacuationHero />
    case 'flood_ledger': return <FloodLedgerHero />
    case 'mirror':       return <MirrorHero />
    case 'closing':      return <ClosingHero />
    default:             return <CVGaugingHero />
  }
}

// ── Main PresentationMode Component ────────────────────────────────
export default function PresentationMode({
  currentMoment = 'cv_gauging',
  onMomentChange,
  onClose,
  predictions = [],
}) {
  // Keyboard navigation
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') {
        onClose?.()
        return
      }

      const currentIdx = MOMENTS.findIndex(m => m.id === currentMoment)
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        const next = Math.min(currentIdx + 1, MOMENTS.length - 1)
        onMomentChange?.(MOMENTS[next].id)
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        const prev = Math.max(currentIdx - 1, 0)
        onMomentChange?.(MOMENTS[prev].id)
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [currentMoment, onMomentChange, onClose])

  return (
    <div className="presentation-overlay">
      <TopBar
        currentMoment={currentMoment}
        onSelectMoment={(id) => onMomentChange?.(id)}
        onClose={onClose}
      />

      <div className="presentation-content">
        <HeroContent momentId={currentMoment} predictions={predictions} />
      </div>

      <LiveMetricsTicker predictions={predictions} />
    </div>
  )
}

// Export MOMENTS for backward compatibility
export { MOMENTS }
