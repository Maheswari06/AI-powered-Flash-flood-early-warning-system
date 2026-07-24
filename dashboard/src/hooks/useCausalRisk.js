/**
 * useCausalRisk — Fetches causal risk analysis data.
 *
 * Exposes causal graph, intervention suggestions, and risk decomposition.
 */

import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

const DEMO_RISK = {
  village_id: 'kullu_01',
  risk_score: 0.73,
  decomposition: {
    rainfall: 0.28,
    water_level: 0.22,
    soil_moisture: 0.12,
    upstream_dam: 0.08,
    community_signal: 0.03,
  },
  causal_edges: [
    { from: 'rainfall', to: 'water_level', strength: 0.85 },
    { from: 'rainfall', to: 'soil_moisture', strength: 0.62 },
    { from: 'water_level', to: 'flood_risk', strength: 0.91 },
    { from: 'soil_moisture', to: 'flood_risk', strength: 0.45 },
    { from: 'upstream_dam', to: 'water_level', strength: 0.38 },
    { from: 'community_signal', to: 'flood_risk', strength: 0.15 },
  ],
  interventions: [
    { action: 'Dam pre-release', effect: -0.15, confidence: 0.72 },
    { action: 'Evacuation trigger', effect: 0, confidence: 0.88, note: 'Does not change risk, saves lives' },
    { action: 'Soil drainage', effect: -0.05, confidence: 0.45 },
  ],
}

export default function useCausalRisk(demoMode = false, villageId = 'kullu_01') {
  const [risk, setRisk] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchRisk = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(API.causalRisk(villageId))
      setRisk(data)
    } catch (err) {
      if (demoMode) {
        setRisk({ ...DEMO_RISK, village_id: villageId })
      } else {
        setError(err.message)
      }
    }
    setLoading(false)
  }, [villageId, demoMode])

  useEffect(() => { fetchRisk() }, [fetchRisk])

  return {
    risk,
    loading,
    error,
    refetch: fetchRisk,
  }
}
