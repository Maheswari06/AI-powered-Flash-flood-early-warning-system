import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { riskColorHex, alertBadgeClass } from '../utils/colorScale'

/**
 * SHAP explanation popup shown when a village dot is clicked.
 *
 * Shows:
 *  - Village name + alert level badge
 *  - Animated circular risk gauge
 *  - SHAP horizontal bar chart (red = increases, blue = decreases)
 *  - Plain-language explanation sentences
 */
export default function VillagePopup({ village, onClose }) {
  const {
    name,
    risk_score,
    alert_level,
    explanation = [],
    confidence,
    timestamp,
    state,
    basin,
  } = village

  const riskPct = Math.round(risk_score * 100)
  const color = riskColorHex(risk_score)

  // SHAP bar chart data
  const chartData = useMemo(
    () =>
      explanation.map((e) => ({
        name: e.factor,
        value: parseFloat(e.contribution_pct?.toFixed(1) ?? 0),
        direction: e.direction,
        displayValue: e.value,
      })),
    [explanation]
  )

  // Circular gauge SVG
  const circumference = 2 * Math.PI * 40
  const dashOffset = circumference - (risk_score * circumference)

  return (
    <div className="absolute top-4 right-4 w-96 bg-navy-light/95 backdrop-blur-md border border-accent/20 rounded-xl shadow-2xl z-50 overflow-hidden font-body">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div>
          <h3 className="font-heading text-lg font-bold text-white">{name}</h3>
          <p className="text-xs text-gray-400">
            {state} · {basin} basin
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={alertBadgeClass(alert_level)}>{alert_level}</span>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Risk gauge + confidence */}
      <div className="flex items-center gap-6 px-4 py-4">
        {/* Circular gauge */}
        <div className="relative flex-shrink-0">
          <svg width="100" height="100" className="-rotate-90">
            <circle
              cx="50"
              cy="50"
              r="40"
              fill="none"
              stroke="#1e293b"
              strokeWidth="8"
            />
            <circle
              cx="50"
              cy="50"
              r="40"
              fill="none"
              stroke={color}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              className="transition-all duration-1000 ease-out"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-heading font-bold" style={{ color }}>
              {riskPct}%
            </span>
            <span className="text-[10px] text-gray-500 uppercase">Risk</span>
          </div>
        </div>

        {/* Meta info */}
        <div className="flex-1 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Confidence</span>
            <span className="text-white font-medium">{confidence}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Updated</span>
            <span className="text-white font-medium">
              {timestamp
                ? new Date(timestamp).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : '—'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Village ID</span>
            <span className="text-accent text-xs font-mono">{village.id}</span>
          </div>
        </div>
      </div>

      {/* SHAP explanation chart */}
      {chartData.length > 0 && (
        <div className="px-4 pb-2">
          <h4 className="font-heading text-sm font-semibold text-accent mb-2">
            Risk Factors (SHAP)
          </h4>
          <ResponsiveContainer width="100%" height={chartData.length * 36 + 10}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 0, right: 10, bottom: 0, left: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#1e293b"
                horizontal={false}
              />
              <XAxis
                type="number"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                domain={[0, 'auto']}
                unit="%"
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#d1d5db', fontSize: 11 }}
                width={140}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: '#0c1a2e',
                  border: '1px solid #00c9ff33',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(val, _name, props) =>
                  [`${val}% — ${props.payload.displayValue}`, 'Contribution']
                }
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={14}>
                {chartData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={
                      entry.direction === 'INCREASES_RISK' ? '#ef4444' : '#3b82f6'
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Plain language explanations */}
      {explanation.length > 0 && (
        <div className="px-4 pb-4 space-y-1">
          {explanation.map((e, i) => (
            <p key={i} className="text-xs text-gray-400">
              <span className="text-white">{e.factor}</span> at{' '}
              <span className="text-accent">{e.value}</span> contributed{' '}
              <span className="text-white font-medium">
                {e.contribution_pct?.toFixed(0)}%
              </span>{' '}
              to risk
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
