import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import VILLAGES from '../data/villages'
import API from '../config/api'

const API_BASE = import.meta.env.VITE_PREDICTION_API || ''
const DEFAULT_POLL = Number(import.meta.env.VITE_POLL_INTERVAL) || 30000
const FAST_POLL = 10000

/**
 * Generate fake predictions that ramp over ~3 minutes for demo mode.
 * Each call increments an internal tick counter.
 */
let demoTick = 0
function generateDemoPredictions() {
  demoTick++
  const progress = Math.min(demoTick / 36, 1) // 36 ticks × 5s ≈ 3 min
  const sigmoid = (x) => 1 / (1 + Math.exp(-10 * (x - 0.5)))

  return VILLAGES.map((v) => {
    // Each village ramps at slightly different rates
    const offset = (v.lat * 0.1 + v.lon * 0.05) % 0.3
    const rawProgress = Math.min(1, progress + offset * progress)
    const risk = sigmoid(rawProgress) * 0.95

    // Classify alert level
    let alert_level = 'NORMAL'
    if (risk >= 0.88) alert_level = 'EMERGENCY'
    else if (risk >= 0.72) alert_level = 'WARNING'
    else if (risk >= 0.55) alert_level = 'WATCH'
    else if (risk >= 0.35) alert_level = 'ADVISORY'

    const explanation = [
      {
        factor: 'Soil saturation index',
        contribution_pct: 35 + risk * 10,
        value: `${(0.4 + risk * 0.5).toFixed(0)}%`,
        direction: 'INCREASES_RISK',
      },
      {
        factor: 'Rainfall intensity (6hr)',
        contribution_pct: 25 + risk * 8,
        value: `${(10 + risk * 80).toFixed(0)} mm`,
        direction: 'INCREASES_RISK',
      },
      {
        factor: 'Rate of change (1hr)',
        contribution_pct: 15 + risk * 5,
        value: `+${(risk * 1.2).toFixed(2)} m/hr`,
        direction: 'INCREASES_RISK',
      },
    ]

    return {
      village_id: v.id,
      risk_score: parseFloat(risk.toFixed(4)),
      alert_level,
      explanation,
      adaptive_threshold: {
        advisory: 0.35,
        watch: 0.55,
        warning: 0.72,
        emergency: 0.88,
        adjustment_reason: 'Monsoon season active → thresholds ×0.90',
      },
      timestamp: new Date().toISOString(),
      confidence: risk > 0.6 ? 'HIGH' : risk > 0.3 ? 'MEDIUM' : 'LOW',
      quality: 'GOOD',
    }
  })
}

/**
 * Hook that polls the prediction API and merges results with village data.
 *
 * @param {boolean} demoMode — if true, use simulated rising-risk data
 * @returns {{ predictions, loading, error, stale, lastUpdated, activeAlerts }}
 */
export default function usePredictions(demoMode = false) {
  const [predictions, setPredictions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [stale, setStale] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const firstLoad = useRef(true)

  // Merge API predictions with static village data
  const mergePredictions = useCallback((apiData) => {
    const predMap = {}
    apiData.forEach((p) => {
      predMap[p.village_id] = p
    })

    return VILLAGES.map((v) => {
      const pred = predMap[v.id]
      return {
        ...v,
        risk_score: pred?.risk_score ?? 0,
        alert_level: pred?.alert_level ?? 'NORMAL',
        explanation: pred?.explanation ?? [],
        adaptive_threshold: pred?.adaptive_threshold ?? null,
        confidence: pred?.confidence ?? 'LOW',
        timestamp: pred?.timestamp ?? null,
        quality: pred?.quality ?? 'UNKNOWN',
      }
    })
  }, [])

  const fetchPredictions = useCallback(async () => {
    if (demoMode) {
      const demo = generateDemoPredictions()
      setPredictions(mergePredictions(demo))
      setLoading(false)
      setStale(false)
      setLastUpdated(new Date())
      setError(null)
      firstLoad.current = false
      return
    }

    try {
      const resp = await axios.get(API.predictions, {
        timeout: 8000,
      })
      setPredictions(mergePredictions(resp.data))
      setStale(false)
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      console.warn('Prediction API error:', err.message)
      setError(err.message)
      setStale(true)
      // Keep showing last known data — don't clear predictions
      if (firstLoad.current) {
        // On first load failure, show villages with zero risk
        setPredictions(mergePredictions([]))
      }
    } finally {
      setLoading(false)
      firstLoad.current = false
    }
  }, [demoMode, mergePredictions])

  // Determine poll interval: faster during active alerts
  const hasActiveAlert = predictions.some(
    (p) => p.alert_level === 'WARNING' || p.alert_level === 'EMERGENCY'
  )
  const interval = demoMode ? 5000 : hasActiveAlert ? FAST_POLL : DEFAULT_POLL

  useEffect(() => {
    fetchPredictions()
    const timer = setInterval(fetchPredictions, interval)
    return () => clearInterval(timer)
  }, [fetchPredictions, interval])

  // Reset demo tick when entering demo mode
  useEffect(() => {
    if (demoMode) demoTick = 0
  }, [demoMode])

  const activeAlerts = predictions.filter(
    (p) =>
      p.alert_level === 'ADVISORY' ||
      p.alert_level === 'WATCH' ||
      p.alert_level === 'WARNING' ||
      p.alert_level === 'EMERGENCY'
  ).length

  return { predictions, loading, error, stale, lastUpdated, activeAlerts }
}
