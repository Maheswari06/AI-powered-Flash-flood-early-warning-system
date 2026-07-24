/**
 * useMirrorData — Fetches counterfactual analysis from MIRROR engine.
 *
 * Exposes event data, counterfactual results, slider data, and custom CF runner.
 */

import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

// Demo fallback
const DEMO_EVENT = {
  event_id: 'himachal_2023',
  name: '2023 Himachal Pradesh Flash Flood (Beas River)',
  date: '2023-07-09',
  location: 'Kullu-Mandi corridor, Himachal Pradesh',
  lives_lost: 71,
  peak_flood_depth_m: 4.7,
  damage_crore_inr: 1847,
  affected_population: 12500,
  official_warning_time_min: -8,
  argus_detection_time_min: -78,
}

const DEMO_COUNTERFACTUALS = [
  {
    cf_id: 'CF_003', cf_label: 'ARGUS Deployed',
    lives_saved_estimate: 44, casualties_estimate: 27,
    peak_depth_m: 4.0, damage_avoided_crore: 280,
    intervention_time_min: -78, confidence: 0.68,
    area_reduction_pct: 12.8,
    description: 'With ARGUS sensor network, anomaly detected at T-78 min.',
    intervention_actions: ['ARGUS anomaly detection at T-78 min', 'Automated CHORUS alert', 'Dam pre-release', 'Multi-channel evacuation'],
  },
  {
    cf_id: 'CF_002', cf_label: 'Early Evacuation',
    lives_saved_estimate: 41, casualties_estimate: 30,
    peak_depth_m: 4.7, damage_avoided_crore: 120,
    intervention_time_min: -90, confidence: 0.81,
    area_reduction_pct: 0,
    description: 'Evacuation order issued at T-90 min instead of T-5 min.',
    intervention_actions: ['Evacuation order at T-90 min', 'NDRF pre-positioned', 'School buses commandeered'],
  },
  {
    cf_id: 'CF_001', cf_label: 'Early Dam Release',
    lives_saved_estimate: 28, casualties_estimate: 43,
    peak_depth_m: 3.67, damage_avoided_crore: 340,
    intervention_time_min: -120, confidence: 0.72,
    area_reduction_pct: 18.5,
    description: 'Proactive 15% gate opening at Pandoh Dam at T-120 min.',
    intervention_actions: ['Pandoh Dam gate opening 15%', 'Downstream warning', 'Controlled drawdown'],
  },
  {
    cf_id: 'CF_004', cf_label: 'Upstream Reforestation',
    lives_saved_estimate: 19, casualties_estimate: 52,
    peak_depth_m: 3.38, damage_avoided_crore: 510,
    intervention_time_min: -9999, confidence: 0.55,
    area_reduction_pct: 24.3,
    description: '40% increase in forest cover across upstream Beas catchment.',
    intervention_actions: ['Reforestation program', 'Riparian buffer zones', 'Check dams', 'Soil conservation'],
  },
]

// Generate demo slider data
function generateDemoSliderData() {
  const data = []
  for (let i = 0; i <= 36; i++) {
    const lead = i * 5
    const maxSaveable = 71 * 0.75
    const livesSaved = Math.round(maxSaveable / (1 + Math.exp(-0.03 * (lead - 45))))
    const depthFactor = Math.max(0.65, 1.0 - 0.002 * lead)
    data.push({
      time_before_peak_min: lead,
      intervention_time_min: -lead,
      lives_saved_estimate: livesSaved,
      peak_depth_m: Math.round(4.7 * depthFactor * 100) / 100,
      damage_reduction_pct: Math.round((1 - depthFactor) * 100 * 0.6 * 10) / 10,
    })
  }
  return data
}

export default function useMirrorData(demoMode = false, eventId = 'himachal_2023') {
  const [event, setEvent] = useState(null)
  const [counterfactuals, setCounterfactuals] = useState([])
  const [sliderData, setSliderData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(API.mirrorCF(eventId))
      setEvent(data.event)
      setCounterfactuals(data.counterfactuals || [])
      setSliderData(data.slider_data || [])
    } catch (err) {
      if (demoMode) {
        setEvent(DEMO_EVENT)
        setCounterfactuals(DEMO_COUNTERFACTUALS)
        setSliderData(generateDemoSliderData())
      } else {
        setError(err.message)
      }
    }
    setLoading(false)
  }, [eventId, demoMode])

  const runCustomCF = useCallback(async (interventionTime, depthFactor = 0.85) => {
    setLoading(true)
    try {
      const { data } = await axios.post(
        API.mirrorCustom(eventId),
        null,
        { params: { intervention_time_min: interventionTime, depth_factor: depthFactor } }
      )
      return data.counterfactual
    } catch {
      // Estimate locally
      const lead = Math.abs(interventionTime)
      const maxSaveable = 71 * 0.75
      const livesSaved = Math.round(maxSaveable / (1 + Math.exp(-0.03 * (lead - 45))))
      return {
        cf_id: `CF_CUSTOM_${lead}`,
        cf_label: `Custom (T-${lead}min)`,
        lives_saved_estimate: livesSaved,
        peak_depth_m: Math.round(4.7 * depthFactor * 100) / 100,
        casualties_estimate: 71 - livesSaved,
      }
    } finally {
      setLoading(false)
    }
  }, [eventId])

  const downloadReport = useCallback(() => {
    window.open(API.mirrorReport(eventId), '_blank')
  }, [eventId])

  useEffect(() => { fetchAll() }, [fetchAll])

  return {
    event,
    counterfactuals,
    sliderData,
    loading,
    error,
    runCustomCF,
    downloadReport,
    refetch: fetchAll,
  }
}
