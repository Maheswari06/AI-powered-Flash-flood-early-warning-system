/**
 * BasinSelector — Multi-basin selection dropdown for the ARGUS dashboard.
 * Fetches live basin summaries from the API; falls back to static defaults.
 * Emits the selected basin to parent for filtering predictions.
 */
import { useState, useRef, useEffect } from 'react'

const BASINS_FALLBACK = [
  {
    id: 'brahmaputra',
    name: 'Brahmaputra Basin',
    region: 'Northeast India',
    stations: 42,
    center: [26.1, 91.7],
    zoom: 8,
    color: '#38bdf8',
  },
  {
    id: 'beas',
    name: 'Beas Basin',
    region: 'Himachal Pradesh',
    stations: 18,
    center: [31.9, 77.1],
    zoom: 9,
    color: '#34d399',
  },
  {
    id: 'godavari',
    name: 'Godavari Basin',
    region: 'Central–South India',
    stations: 35,
    center: [19.0, 79.5],
    zoom: 7,
    color: '#fbbf24',
  },
]

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function BasinSelector({ selectedBasin, onBasinChange, className = '' }) {
  const [open, setOpen] = useState(false)
  const [basins, setBasins] = useState(BASINS_FALLBACK)
  const ref = useRef(null)

  const current = basins.find((b) => b.id === selectedBasin) || basins[0]

  // Fetch live basin summaries from API
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/api/v1/basins/summaries`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setBasins(data)
        }
      })
      .catch(() => {
        // Keep fallback basins on error
      })
    return () => controller.abort()
  }, [])

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* Trigger */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm transition"
      >
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: current.color }}
        />
        <span className="font-semibold text-slate-100 truncate max-w-[160px]">
          {current.name}
        </span>
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-slate-800 border border-slate-600 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2">
          <div className="px-3 py-2 border-b border-slate-700">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Select River Basin
            </span>
          </div>
          <ul className="py-1">
            {basins.map((basin) => (
              <li key={basin.id}>
                <button
                  onClick={() => {
                    onBasinChange(basin.id, basin)
                    setOpen(false)
                  }}
                  className={`w-full text-left px-3 py-2.5 flex items-start gap-3 transition ${
                    basin.id === selectedBasin
                      ? 'bg-sky-500/10'
                      : 'hover:bg-slate-700/50'
                  }`}
                >
                  <span
                    className="w-3 h-3 rounded-full shrink-0 mt-0.5"
                    style={{ backgroundColor: basin.color }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-slate-100">
                        {basin.name}
                      </span>
                      {basin.id === selectedBasin && (
                        <svg className="w-4 h-4 text-sky-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {basin.region} · {basin.stations} stations
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
          <div className="px-3 py-2 border-t border-slate-700 text-xs text-slate-500">
            Multi-basin monitoring powered by HYDRA
          </div>
        </div>
      )}
    </div>
  )
}

export { BASINS_FALLBACK as BASINS }
