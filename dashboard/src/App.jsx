import { useState, useEffect, lazy, Suspense } from 'react'

// Phase 1 components (always loaded — lightweight)
import ARGUSMap from './components/ARGUSMap'
import MetricsBar from './components/MetricsBar'
import AlertSidebar from './components/AlertSidebar'
import RiskLegend from './components/RiskLegend'
import ACNStatus from './components/ACNStatus'
import SystemHealth from './components/SystemHealth'

// Phase 2 components (lazy-loaded — heavier panels)
const EvacuationMap = lazy(() => import('./components/EvacuationMap'))
const MirrorPanel = lazy(() => import('./components/MirrorPanel'))
const FloodLedger = lazy(() => import('./components/FloodLedger'))
import ChorusActivity from './components/ChorusActivity'

// Phase 3 components (lazy-loaded)
const ScarNetPanel = lazy(() => import('./components/ScarNetPanel'))
const PresentationMode = lazy(() => import('./components/PresentationMode'))
import DemoController from './components/DemoController'

// Phase 7 components (lazy-loaded — gap-closure panels)
const GaugeHeroPanel = lazy(() => import('./components/GaugeHeroPanel'))
const NDMACompliancePanel = lazy(() => import('./components/NDMACompliancePanel'))
const DroneMapPanel = lazy(() => import('./components/DroneMapPanel'))
const LiveValidationPanel = lazy(() => import('./components/LiveValidationPanel'))
const DisplacementMap = lazy(() => import('./components/DisplacementMap'))

// Phase 6: ARGUS Copilot (always loaded — lightweight chat UI)
import ARGUSCopilot from './components/ARGUSCopilot'

import usePredictions from './hooks/usePredictions'
import useAlertLog from './hooks/useAlertLog'

// Presentation CSS
import './styles/presentation.css'

/**
 * Root layout — Phase 3 Final:
 *
 *  ┌──────────── MetricsBar ── SystemHealth ─────────────┐
 *  │ HYDRA ARGUS │ stats...     │ Health │ DEMO toggle   │
 *  ├─────────────────────────────────────────────────────┤
 *  │ [🗺 Risk] [🚌 Evac] [🔮 MIRROR] [🔗 Ledger]       │
 *  │ [📢 CHORUS] [🛰️ ScarNet] [🎬 Controller]           │
 *  ├─────────────────────────────┬───────────────────────┤
 *  │                             │                       │
 *  │     Active Tab Content      │   AlertSidebar        │
 *  │                             │                       │
 *  └─────────────────────────────┴───────────────────────┘
 *
 *  PresentationMode: z-50 fullscreen overlay (F11 / button)
 */

const TABS = [
  { id: 'gauges',        label: 'Gauges',       icon: '📊',  shortcut: '1' },
  { id: 'risk_map',      label: 'Risk Map',     icon: '🗺️',  shortcut: '2' },
  { id: 'ndma',          label: 'NDMA',         icon: '🇮🇳',  shortcut: '3' },
  { id: 'drones',        label: 'Drones',       icon: '🚁',  shortcut: '4' },
  { id: 'evacuation',    label: 'Evacuation',   icon: '🚌',  shortcut: '5' },
  { id: 'displacement',  label: 'Displaced',    icon: '🏕️',  shortcut: '6' },
  { id: 'validation',    label: 'Validation',   icon: '🔬',  shortcut: '7' },
  { id: 'mirror',        label: 'MIRROR',       icon: '🔮',  shortcut: '8' },
  { id: 'flood_ledger',  label: 'FloodLedger',  icon: '🔗',  shortcut: '9' },
  { id: 'chorus',        label: 'CHORUS',       icon: '📢',  shortcut: '0' },
  { id: 'scarnet',       label: 'ScarNet',      icon: '🛰️',  shortcut: '' },
  { id: 'controller',    label: 'Controller',   icon: '🎬',  shortcut: '' },
]

function LazyFallback() {
  return (
    <div className="flex-1 flex items-center justify-center bg-navy">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-gray-500 font-body text-xs">Loading panel...</p>
      </div>
    </div>
  )
}

export default function App() {
  const [demoMode, setDemoMode] = useState(true)
  const [activeTab, setActiveTab] = useState('risk_map')
  const [presenting, setPresenting] = useState(false)
  const [currentMoment, setCurrentMoment] = useState('cv_gauging')

  const { predictions, loading, stale, lastUpdated, activeAlerts } =
    usePredictions(demoMode)

  const { alerts, loading: alertsLoading } = useAlertLog(demoMode)

  // Compute max risk for Phase 2 panels
  const maxRisk = predictions.length > 0
    ? Math.max(...predictions.map((p) => p.risk_score || 0))
    : 0

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      // Alt+1-9,0 for tabs
      if (e.altKey && e.key >= '0' && e.key <= '9') {
        e.preventDefault()
        const tab = TABS.find(t => t.shortcut === e.key)
        if (tab) setActiveTab(tab.id)
        return
      }
      // F11 toggles presentation mode
      if (e.key === 'F11') {
        e.preventDefault()
        setPresenting(p => !p)
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const renderTabContent = () => {
    switch (activeTab) {
      case 'gauges':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto p-4">
              <GaugeHeroPanel />
            </div>
          </Suspense>
        )

      case 'risk_map':
        return (
          <div className="flex-1 relative">
            {loading && predictions.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center bg-navy">
                <div className="text-center">
                  <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-gray-400 font-body text-sm">Loading predictions...</p>
                </div>
              </div>
            ) : (
              <ARGUSMap predictions={predictions} />
            )}
            <RiskLegend />
            <ACNStatus predictions={predictions} demoMode={demoMode} />
          </div>
        )

      case 'evacuation':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto">
              <EvacuationMap
                selectedVillage="kullu_01"
                riskScore={maxRisk}
                demoMode={demoMode}
                fullScreen={true}
              />
            </div>
          </Suspense>
        )

      case 'mirror':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto">
              <MirrorPanel demoMode={demoMode} fullScreen={true} />
            </div>
          </Suspense>
        )

      case 'flood_ledger':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto">
              <FloodLedger demoMode={demoMode} fullScreen={true} />
            </div>
          </Suspense>
        )

      case 'chorus':
        return (
          <div className="flex-1 relative overflow-auto">
            <ChorusActivity demoMode={demoMode} fullScreen={true} />
          </div>
        )

      case 'scarnet':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto">
              <ScarNetPanel demoMode={demoMode} fullScreen={true} />
            </div>
          </Suspense>
        )

      case 'controller':
        return (
          <div className="flex-1 relative overflow-auto">
            <DemoController
              currentMoment={currentMoment}
              onMomentChange={setCurrentMoment}
              onPresent={() => setPresenting(p => !p)}
              isPresenting={presenting}
            />
          </div>
        )

      case 'ndma':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto p-4">
              <NDMACompliancePanel />
            </div>
          </Suspense>
        )

      case 'drones':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto p-4">
              <DroneMapPanel />
            </div>
          </Suspense>
        )

      case 'displacement':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto p-4">
              <DisplacementMap />
            </div>
          </Suspense>
        )

      case 'validation':
        return (
          <Suspense fallback={<LazyFallback />}>
            <div className="flex-1 relative overflow-auto p-4">
              <LiveValidationPanel />
            </div>
          </Suspense>
        )

      default:
        return null
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-navy overflow-hidden">
      {/* Presentation mode overlay */}
      {presenting && (
        <Suspense fallback={<LazyFallback />}>
          <PresentationMode
            currentMoment={currentMoment}
            onMomentChange={setCurrentMoment}
            onClose={() => setPresenting(false)}
            predictions={predictions}
          />
        </Suspense>
      )}

      {/* Top bar */}
      <MetricsBar
        predictions={predictions}
        activeAlerts={activeAlerts}
        lastUpdated={lastUpdated}
        stale={stale}
        demoMode={demoMode}
        onToggleDemo={() => setDemoMode((prev) => !prev)}
      />

      {/* Tab navigation */}
      <div className="flex items-center gap-1 px-4 py-1.5 bg-gray-900/80 border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono transition-all ${
              activeTab === tab.id
                ? 'bg-accent/20 text-accent border border-accent/40 shadow-lg shadow-accent/10'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/60 border border-transparent'
            }`}
            title={tab.shortcut ? `Alt+${tab.shortcut}` : tab.label}
          >
            <span className="text-sm">{tab.icon}</span>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}

        {/* System Health badge */}
        <div className="ml-2 border-l border-gray-800 pl-2">
          <SystemHealth />
        </div>

        {/* Live status indicators */}
        <div className="ml-auto flex items-center gap-3 text-[10px] text-gray-500">
          {predictions.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              {predictions.length} stations
            </span>
          )}
          {activeAlerts > 0 && (
            <span className="flex items-center gap-1 text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              {activeAlerts} alerts
            </span>
          )}
          {/* Presentation mode quick toggle */}
          <button
            onClick={() => setPresenting(p => !p)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] hover:bg-gray-800/60 transition-colors"
            title="F11 — Toggle Presentation Mode"
          >
            <span>🎬</span>
            <span className="hidden md:inline text-gray-500">Present</span>
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {renderTabContent()}

        {/* Alert sidebar — always visible */}
        <AlertSidebar alerts={alerts} loading={alertsLoading} />
      </div>

      {/* Phase 6: ARGUS Copilot — floating bottom-right */}
      <ARGUSCopilot district="Majuli" userRole="DISTRICT_MAGISTRATE" />
    </div>
  )
}
