/**
 * Color-coded risk level legend overlay — bottom-left of map.
 */
export default function RiskLegend() {
  const levels = [
    { label: 'Normal', range: '< 0.35', color: '#22c55e' },
    { label: 'Advisory', range: '0.35–0.55', color: '#eab308' },
    { label: 'Watch', range: '0.55–0.72', color: '#f97316' },
    { label: 'Warning', range: '0.72–0.88', color: '#ef4444' },
    { label: 'Emergency', range: '≥ 0.88', color: '#dc2626' },
  ]

  return (
    <div className="absolute bottom-6 left-4 bg-navy-light/90 backdrop-blur-md border border-white/10 rounded-lg px-3 py-2 z-[1000]">
      <h4 className="font-heading text-xs font-semibold text-accent mb-1.5 tracking-wide uppercase">
        Risk Level
      </h4>
      <div className="space-y-1">
        {levels.map((l) => (
          <div key={l.label} className="flex items-center gap-2 text-xs font-body">
            <span
              className="w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: l.color }}
            />
            <span className="text-gray-300 w-18">{l.label}</span>
            <span className="text-gray-500 tabular-nums">{l.range}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
