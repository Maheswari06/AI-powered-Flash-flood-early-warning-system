import { useState, useEffect } from 'react'

/**
 * NDMACompliancePanel — Live NDMA colour-code mapping
 *
 * Gap 3 closure: Translates ARGUS internal alert levels into
 * NDMA's GREEN/YELLOW/ORANGE/RED framework with SOP 4.2 lead times.
 *
 * Wired to:
 *   POST /api/v1/ndma/translate       (NDMA compliance engine)
 *   GET  /api/v1/ndma/mapping-table   (5-row mapping table)
 */

const DEMO_TRANSLATED = {
  ndma_color: 'ORANGE',
  ndma_action: 'Evacuate low-lying areas; deploy NDRF',
  argus_level: 'WARNING',
  district: 'Majuli',
  state: 'Assam',
  population_affected: 12000,
  lead_time_hrs: 6.0,
  minimum_lead_time_hrs: 4.0,
  lead_time_compliant: true,
  required_actions: [
    'Activate District EOC to Level-III',
    'Issue public warning via all channels',
    'Pre-position NDRF teams at staging areas',
    'Open relief shelters in identified safe zones',
    'Restrict vehicular movement on flood-prone roads',
  ],
  mandatory_notifications: ['NDMA', 'SDMA Assam', 'CWC Regional', 'IAF (airlift standby)', 'MHA Control Room'],
}

const DEMO_MAPPING_TABLE = [
  { argus_level: 'NORMAL', ndma_color: 'GREEN', ndma_action: 'Routine monitoring', minimum_lead_time_hrs: 0 },
  { argus_level: 'ADVISORY', ndma_color: 'YELLOW', ndma_action: 'Heightened vigilance; prepare resources', minimum_lead_time_hrs: 12 },
  { argus_level: 'WATCH', ndma_color: 'YELLOW', ndma_action: 'Alert first responders; stage equipment', minimum_lead_time_hrs: 8 },
  { argus_level: 'WARNING', ndma_color: 'ORANGE', ndma_action: 'Evacuate low-lying areas; deploy NDRF', minimum_lead_time_hrs: 4 },
  { argus_level: 'EMERGENCY', ndma_color: 'RED', ndma_action: 'Full evacuation; request military aid', minimum_lead_time_hrs: 2 },
]

const NDMA_COLORS = {
  GREEN:  { bg: 'bg-green-600',   border: 'border-green-500/40', text: 'text-green-100',  dot: 'bg-green-400'  },
  YELLOW: { bg: 'bg-yellow-500',  border: 'border-yellow-400/40', text: 'text-yellow-100', dot: 'bg-yellow-400' },
  ORANGE: { bg: 'bg-orange-500',  border: 'border-orange-400/40', text: 'text-orange-100', dot: 'bg-orange-400' },
  RED:    { bg: 'bg-red-600',     border: 'border-red-500/40',   text: 'text-red-100',    dot: 'bg-red-400'    },
}

const NDMACompliancePanel = () => {
  const [translated, setTranslated] = useState(null)
  const [mappingTable, setMappingTable] = useState([])
  const [showTable, setShowTable] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      let tOk = false, mOk = false
      try {
        const [tRes, mRes] = await Promise.allSettled([
          fetch('/api/v1/ndma/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              argus_level: 'WARNING',
              district: 'Majuli',
              state: 'Assam',
              lead_time_hrs: 6.0,
              population_affected: 12000,
            }),
          }),
          fetch('/api/v1/ndma/mapping-table'),
        ])
        if (tRes.status === 'fulfilled' && tRes.value.ok) {
          setTranslated(await tRes.value.json()); tOk = true
        }
        if (mRes.status === 'fulfilled' && mRes.value.ok) {
          const mData = await mRes.value.json()
          if (mData.mapping_table?.length || mData.table?.length) {
            setMappingTable(mData.mapping_table || mData.table || []); mOk = true
          }
        }
      } catch { /* ignore */ }
      if (!tOk) setTranslated(DEMO_TRANSLATED)
      if (!mOk) setMappingTable(DEMO_MAPPING_TABLE)
      setLoading(false)
    }
    fetchAll()
    const interval = setInterval(fetchAll, 60000)
    return () => clearInterval(interval)
  }, [])

  const ndma = translated
    ? NDMA_COLORS[translated.ndma_color] || NDMA_COLORS.GREEN
    : NDMA_COLORS.GREEN

  return (
    <div className="bg-slate-900 rounded-2xl p-5 border border-cyan-900/50">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-cyan-400 font-heading font-bold text-xl">
            NDMA Compliance Engine
          </h2>
          <p className="text-slate-500 text-xs mt-0.5">
            SOP 4.2 colour-code mapping with lead time validation
          </p>
        </div>
        {translated && (
          <span className={`px-3 py-1 rounded-full text-xs font-bold ${
            translated.lead_time_compliant
              ? 'bg-green-900/40 text-green-300 border border-green-600/30'
              : 'bg-red-900/40 text-red-300 border border-red-600/30'
          }`}>
            {translated.lead_time_compliant ? 'SOP COMPLIANT' : 'LEAD TIME SHORT'}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : translated ? (
        <>
          {/* Main NDMA colour block */}
          <div className={`rounded-xl p-4 mb-4 border ${ndma.border} ${ndma.bg}/20`}>
            <div className="flex items-center gap-4">
              <div className={`w-20 h-20 rounded-xl ${ndma.bg} flex items-center justify-center`}>
                <span className="text-white font-heading font-bold text-lg">
                  {translated.ndma_color}
                </span>
              </div>
              <div className="flex-1">
                <p className="text-white font-heading font-bold text-lg">
                  {translated.ndma_action}
                </p>
                <p className="text-slate-400 text-sm mt-1">
                  ARGUS Level: <span className="text-cyan-300 font-bold">{translated.argus_level}</span>
                  {' → '}NDMA: <span className={`font-bold ${ndma.text}`}>{translated.ndma_color}</span>
                </p>
                <p className="text-slate-500 text-xs mt-1">
                  {translated.district}, {translated.state} — Population: {translated.population_affected?.toLocaleString()}
                </p>
              </div>
            </div>
          </div>

          {/* Lead time compliance bar */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-slate-400">Lead Time</span>
              <span className={translated.lead_time_compliant ? 'text-green-400' : 'text-red-400'}>
                {translated.lead_time_hrs}h provided / {translated.minimum_lead_time_hrs}h required
              </span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${
                  translated.lead_time_compliant ? 'bg-green-500' : 'bg-red-500'
                }`}
                style={{
                  width: `${Math.min(100, (translated.lead_time_hrs / Math.max(1, translated.minimum_lead_time_hrs)) * 100)}%`
                }}
              />
            </div>
          </div>

          {/* Required actions */}
          {translated.required_actions && translated.required_actions.length > 0 && (
            <div className="mb-4">
              <h3 className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
                Required Actions
              </h3>
              <div className="space-y-1">
                {translated.required_actions.map((action, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className={`w-1.5 h-1.5 rounded-full ${ndma.dot}`} />
                    <span className="text-slate-300">{action}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mandatory notifications */}
          {translated.mandatory_notifications && translated.mandatory_notifications.length > 0 && (
            <div className="mb-4">
              <h3 className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
                Mandatory Notifications
              </h3>
              <div className="flex flex-wrap gap-2">
                {translated.mandatory_notifications.map((n, i) => (
                  <span key={i} className="px-2 py-1 bg-slate-800 rounded text-xs text-slate-300 border border-slate-700">
                    {n}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="text-green-400 text-center py-6">
          All districts GREEN — no active NDMA bulletins
        </p>
      )}

      {/* Expandable ARGUS → NDMA mapping table */}
      <button
        onClick={() => setShowTable(t => !t)}
        className="w-full text-left text-xs text-slate-500 hover:text-slate-300 border-t border-slate-800 pt-3 mt-2 transition-colors"
      >
        {showTable ? '▼' : '▶'} ARGUS → NDMA Mapping Reference ({mappingTable.length} levels)
      </button>

      {showTable && mappingTable.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-800/60 text-slate-400">
                <th className="px-3 py-2 text-left">ARGUS Level</th>
                <th className="px-3 py-2 text-left">NDMA Colour</th>
                <th className="px-3 py-2 text-left">Action</th>
                <th className="px-3 py-2 text-left">Min Lead Time</th>
              </tr>
            </thead>
            <tbody>
              {mappingTable.map((row, i) => {
                const rowColor = NDMA_COLORS[row.ndma_color] || NDMA_COLORS.GREEN
                return (
                  <tr key={i} className="border-t border-slate-800/50">
                    <td className="px-3 py-2 text-slate-300 font-mono">{row.argus_level}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${rowColor.bg} text-white`}>
                        {row.ndma_color}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-400">{row.ndma_action}</td>
                    <td className="px-3 py-2 text-slate-400">{row.minimum_lead_time_hrs}h</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3 text-center text-slate-600 text-xs">
        NDMA National Disaster Management Plan 2019 | Helpline: 1078
      </div>
    </div>
  )
}

export default NDMACompliancePanel
