import { useState, useEffect } from 'react'
import MOMENTS from '../config/moments'

/**
 * DemoController — Presenter's backstage control panel
 *
 * 7-moment grid with icons, descriptions, and live status.
 * "PRESENT" button launches PresentationMode.
 * Arrow keys navigate between moments.
 *
 * ┌──────────────────────────────────┐
 * │  🎬 Demo Controller             │
 * │  [PRESENT] button               │
 * │                                  │
 * │  ┌────┐ ┌────┐ ┌────┐ ┌────┐   │
 * │  │ CV │ │SHAP│ │Caus│ │ ACN│   │
 * │  └────┘ └────┘ └────┘ └────┘   │
 * │  ┌────┐ ┌────┐ ┌────┐          │
 * │  │Evac│ │ FL │ │Mirr│          │
 * │  └────┘ └────┘ └────┘          │
 * └──────────────────────────────────┘
 */

const MOMENT_DESCRIPTIONS = {
  cv_gauging:   'CCTV water-level extraction via OpenCV. Show real-time feed accuracy.',
  shap_xai:     'SHAP waterfall — why ARGUS flagged the village. Full transparency.',
  causal:       'Live causal intervention: simulate dam pre-release, see risk drop.',
  offline_acn:  'Kill WiFi → show ACN mesh recovery. Zero alert loss.',
  evacuation:   'RL-optimized vehicle routing for Majuli Island. 825 people in 38 min.',
  flood_ledger: 'Blockchain audit trail + automatic parametric insurance payouts.',
  mirror:       'Counterfactual analysis: "If ARGUS existed in 2023, 64 lives saved."',
}

const MOMENT_TIPS = {
  cv_gauging:   'Tip: Highlight the ±3cm accuracy vs traditional sensors.',
  shap_xai:     'Tip: Focus on soil saturation as the dominant factor.',
  causal:       'Tip: Click the intervention button LIVE to show the risk drop.',
  offline_acn:  'Tip: Click "Kill WiFi" and watch the mesh activate.',
  evacuation:   'Tip: Point out multi-trip optimization and road closure handling.',
  flood_ledger: 'Tip: Emphasize tamper-proof chain and automatic claim trigger.',
  mirror:       'Tip: Drag the slider slowly — the "lives saved" counter is powerful.',
}

export default function DemoController({
  currentMoment,
  onMomentChange,
  onPresent,
  isPresenting = false,
}) {
  const [elapsed, setElapsed] = useState(0)

  // Demo timer
  useEffect(() => {
    const timer = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  const currentIdx = MOMENTS.findIndex(m => m.id === currentMoment)
  const currentMeta = MOMENTS[currentIdx]

  return (
    <div className="p-4 overflow-auto flex-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-xl">🎬</span>
          <div>
            <h2 className="font-heading text-lg font-bold text-white">
              Demo Controller
            </h2>
            <p className="text-[11px] text-gray-500">
              Backstage · {formatTime(elapsed)} elapsed
            </p>
          </div>
        </div>

        <button
          onClick={onPresent}
          className={`px-5 py-2 rounded-xl font-heading font-bold text-sm transition-all ${
            isPresenting
              ? 'bg-red-500/20 text-red-400 border border-red-500/40 hover:bg-red-500/30'
              : 'bg-accent/20 text-accent border border-accent/40 hover:bg-accent/30 hover:shadow-lg hover:shadow-accent/20'
          }`}
        >
          {isPresenting ? '⏹ EXIT PRESENT' : '▶ PRESENT'}
        </button>
      </div>

      {/* Current moment detail */}
      {currentMeta && (
        <div className="glass-card-accent p-4 mb-4 animate-fade-in" key={currentMoment}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">{currentMeta.icon}</span>
            <div>
              <div className="font-heading font-bold text-white">
                {currentIdx + 1}. {currentMeta.label}
              </div>
              <div className="text-[11px] text-gray-400 font-body">
                {MOMENT_DESCRIPTIONS[currentMoment]}
              </div>
            </div>
          </div>
          <div className="text-[10px] text-amber-400/80 font-code mt-2 p-2 bg-amber-500/5 rounded">
            {MOMENT_TIPS[currentMoment]}
          </div>
        </div>
      )}

      {/* Moment grid */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {MOMENTS.map((m, i) => (
          <button
            key={m.id}
            onClick={() => onMomentChange(m.id)}
            className={`demo-moment-card ${m.id === currentMoment ? 'active' : ''}`}
          >
            <div className="text-center">
              <span className="text-xl block mb-1">{m.icon}</span>
              <span className="text-[10px] font-heading text-gray-300 block">
                {m.shortLabel}
              </span>
              <span className="text-[9px] text-gray-600 font-code">
                {i + 1}/{MOMENTS.length}
              </span>
            </div>
          </button>
        ))}
      </div>

      {/* Navigation hints */}
      <div className="glass-card p-3">
        <div className="text-[10px] text-gray-500 font-code space-y-1">
          <div className="flex items-center gap-2">
            <kbd className="px-1 py-0.5 rounded bg-gray-800 text-gray-400 text-[9px]">←</kbd>
            <kbd className="px-1 py-0.5 rounded bg-gray-800 text-gray-400 text-[9px]">→</kbd>
            <span>Navigate moments</span>
          </div>
          <div className="flex items-center gap-2">
            <kbd className="px-1 py-0.5 rounded bg-gray-800 text-gray-400 text-[9px]">F11</kbd>
            <span>Toggle presentation mode</span>
          </div>
          <div className="flex items-center gap-2">
            <kbd className="px-1 py-0.5 rounded bg-gray-800 text-gray-400 text-[9px]">Esc</kbd>
            <span>Exit presentation</span>
          </div>
          <div className="flex items-center gap-2">
            <kbd className="px-1 py-0.5 rounded bg-gray-800 text-gray-400 text-[9px]">Alt+1-7</kbd>
            <span>Switch tabs</span>
          </div>
        </div>
      </div>
    </div>
  )
}
