/**
 * useChorusSignals — Fetches CHORUS community intelligence with polling.
 *
 * Exposes stats, village aggregations, signal feed, and demo generation.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import API from '../config/api'

const DEMO_SIGNALS = [
  {
    id: 's1', village_id: 'majuli_01', timestamp: new Date().toISOString(),
    classification: 'FLOOD_WARNING', language: 'as', trust_weight: 0.89,
    text: 'পানীৰ স্তৰ বাঢ়িছে, ঘৰৰ সন্মুখত পানী আহিছে', sentiment: 'PANIC',
    location: { lat: 26.95, lng: 94.17 },
  },
  {
    id: 's2', village_id: 'kullu_01', timestamp: new Date().toISOString(),
    classification: 'INFRASTRUCTURE_DAMAGE', language: 'hi', trust_weight: 0.72,
    text: 'पुल टूट गया है, रास्ता बंद है', sentiment: 'ANXIOUS',
    location: { lat: 31.96, lng: 77.11 },
  },
  {
    id: 's3', village_id: 'mandi_01', timestamp: new Date().toISOString(),
    classification: 'WEATHER_REPORT', language: 'hi', trust_weight: 0.65,
    text: 'बहुत तेज बारिश हो रही है, नदी का पानी बढ़ रहा है', sentiment: 'CONCERNED',
    location: { lat: 31.71, lng: 76.93 },
  },
  {
    id: 's4', village_id: 'dhemaji_01', timestamp: new Date().toISOString(),
    classification: 'STATUS_UPDATE', language: 'en', trust_weight: 0.55,
    text: 'Water level normal, no flooding observed', sentiment: 'CALM',
    location: { lat: 27.48, lng: 94.58 },
  },
]

export default function useChorusSignals(demoMode = false) {
  const [stats, setStats] = useState(null)
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(false)
  const wsRef = useRef(null)

  const fetchStats = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await axios.get(API.chorusStats)
      setStats(data)
    } catch {
      if (demoMode) {
        setStats({
          total_reports: 42,
          villages_reporting: 5,
          consensus_active: true,
          aggregations: {
            majuli_01: { village_id: 'majuli_01', report_count: 15, dominant_sentiment: 'PANIC', panic_ratio: 0.4, avg_credibility: 0.71, flood_mention_rate: 0.93, community_risk_boost: 0.173, top_keywords: ['flood', 'submerged', 'rescue', 'emergency'] },
            kullu_01: { village_id: 'kullu_01', report_count: 12, dominant_sentiment: 'ANXIOUS', panic_ratio: 0.167, avg_credibility: 0.62, flood_mention_rate: 0.75, community_risk_boost: 0.108, top_keywords: ['baadh', 'paani', 'bachao'] },
            mandi_01: { village_id: 'mandi_01', report_count: 8, dominant_sentiment: 'CONCERNED', panic_ratio: 0.0, avg_credibility: 0.55, flood_mention_rate: 0.5, community_risk_boost: 0.05, top_keywords: ['baarish', 'nadi'] },
            dhemaji_01: { village_id: 'dhemaji_01', report_count: 4, dominant_sentiment: 'CALM', panic_ratio: 0.0, avg_credibility: 0.45, flood_mention_rate: 0.25, community_risk_boost: 0.025, top_keywords: ['normal'] },
          },
        })
        setSignals(DEMO_SIGNALS)
      }
    }
    setLoading(false)
  }, [demoMode])

  const generateDemo = useCallback(async (villageId = 'kullu_01', count = 5) => {
    try {
      await axios.post(API.chorusDemoGenerate(villageId, count))
      await fetchStats()
    } catch {
      // Add demo signal
      setSignals(prev => [{
        id: `s_${Date.now()}`,
        village_id: villageId,
        timestamp: new Date().toISOString(),
        classification: 'FLOOD_WARNING',
        language: 'hi',
        trust_weight: Math.round(Math.random() * 40 + 50) / 100,
        text: 'Demo community report — flood warning',
        sentiment: 'ANXIOUS',
      }, ...prev].slice(0, 20))
    }
  }, [fetchStats])

  // WebSocket connection attempt (graceful fallback to polling)
  useEffect(() => {
    if (!demoMode) {
      try {
        const wsUrl = API.chorusWS
        const ws = new WebSocket(wsUrl)
        ws.onmessage = (evt) => {
          try {
            const signal = JSON.parse(evt.data)
            setSignals(prev => [signal, ...prev].slice(0, 50))
          } catch { /* invalid JSON */ }
        }
        ws.onerror = () => ws.close()
        wsRef.current = ws
        return () => ws.close()
      } catch { /* WebSocket not available, use polling */ }
    }
  }, [demoMode])

  useEffect(() => { fetchStats() }, [fetchStats])
  useEffect(() => {
    const iv = setInterval(fetchStats, demoMode ? 8000 : 30000)
    return () => clearInterval(iv)
  }, [fetchStats, demoMode])

  return {
    stats,
    signals,
    loading,
    generateDemo,
    refetch: fetchStats,
  }
}
