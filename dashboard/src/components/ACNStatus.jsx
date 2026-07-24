import VILLAGES from '../data/villages'

/**
 * ACN node status panel — shows which ACN nodes are online/offline.
 * In demo mode, simulates one node going offline after a delay.
 */
export default function ACNStatus({ predictions, demoMode }) {
  const acnVillages = VILLAGES.filter((v) => v.acn_node)

  // In demo mode, simulate Majuli node going offline after some alerts
  const demoOffline = demoMode
    ? predictions.some(
        (p) => p.id === 'VIL-AS-MAJULI' && p.risk_score > 0.6
      )
    : false

  return (
    <div className="absolute bottom-6 right-4 bg-navy-light/90 backdrop-blur-md border border-white/10 rounded-lg px-3 py-2 z-[1000] w-56">
      <h4 className="font-heading text-xs font-semibold text-accent mb-2 tracking-wide uppercase">
        ACN Nodes
      </h4>
      <div className="space-y-2">
        {acnVillages.map((v) => {
          const pred = predictions.find((p) => p.id === v.id)
          const isOffline = demoMode && v.acn_node === 'majuli' && demoOffline

          return (
            <div
              key={v.id}
              className="flex items-center justify-between text-xs font-body"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    isOffline
                      ? 'bg-yellow-500 animate-pulse'
                      : 'bg-green-500'
                  }`}
                />
                <span className="text-gray-300">{v.name}</span>
              </div>
              <span
                className={`font-heading text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${
                  isOffline
                    ? 'bg-yellow-900/40 text-yellow-400'
                    : 'bg-green-900/40 text-green-400'
                }`}
              >
                {isOffline ? 'OFFLINE — ORACLE ACTIVE' : 'ONLINE'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
