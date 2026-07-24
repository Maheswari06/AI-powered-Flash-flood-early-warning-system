/**
 * useEvacuationPlan — Fetches evacuation plan from RL Evacuation Engine.
 *
 * Exposes plan data, village details, notifications, and demo trigger.
 */

import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

// Demo fallback data
const DEMO_PLAN = {
  scenario_id: 'majuli_demo',
  scenario_name: 'Majuli Island Emergency',
  total_people_covered: 6090,
  estimated_completion_minutes: 85,
  vehicles_deployed: 4,
  shelters_used: 3,
  confidence: 0.78,
  planner_mode: 'rule_based',
  assignments: [
    {
      village_id: 'ward_7', village_name: 'Ward 7 (Kamalabari East)', population: 2340,
      vehicle_id: 'BUS_001', vehicle_type: 'bus', route_id: 'NH_715_N',
      shelter_id: 'JORHAT_HALL', eta_minutes: 42, priority: 1, status: 'pending',
      trips_needed: 39, road_closure_warning: true,
      departure_cutoff_utc: new Date(Date.now() + 45 * 60000).toISOString(),
    },
    {
      village_id: 'ward_12', village_name: 'Ward 12 (Jengraimukh)', population: 1680,
      vehicle_id: 'TRUCK_001', vehicle_type: 'truck', route_id: 'SH_23',
      shelter_id: 'GOLAGHAT_CAMP', eta_minutes: 38, priority: 2, status: 'pending',
      trips_needed: 21, road_closure_warning: true,
      departure_cutoff_utc: new Date(Date.now() + 55 * 60000).toISOString(),
    },
    {
      village_id: 'kamalabari', village_name: 'Kamalabari', population: 1180,
      vehicle_id: 'BUS_002', vehicle_type: 'bus', route_id: 'FR_12',
      shelter_id: 'NIMATI_SCHOOL', eta_minutes: 35, priority: 3, status: 'pending',
      trips_needed: 27, road_closure_warning: false,
      departure_cutoff_utc: new Date(Date.now() + 50 * 60000).toISOString(),
    },
    {
      village_id: 'garamur', village_name: 'Garamur', population: 890,
      vehicle_id: 'BOAT_001', vehicle_type: 'boat', route_id: 'BOAT_ROUTE',
      shelter_id: 'JORHAT_HALL', eta_minutes: 55, priority: 4, status: 'pending',
      trips_needed: 36, road_closure_warning: false,
      departure_cutoff_utc: new Date(Date.now() + 70 * 60000).toISOString(),
    },
  ],
}

const DEMO_NOTIFICATIONS = [
  { time: new Date().toISOString(), level: 'CRITICAL', message: '🚨 Ward 7: IMMEDIATE EVACUATION — 2340 people, BUS_001 via NH_715_N → Jorhat Hall (ETA 42 min, road closes in 67 min)' },
  { time: new Date().toISOString(), level: 'URGENT', message: '⚠️ Ward 12: HIGH PRIORITY — 1680 people, TRUCK_001 via SH_23 → Golaghat Camp (ETA 38 min, road closes in 55 min)' },
  { time: new Date().toISOString(), level: 'WARN', message: '📢 Kamalabari: EVACUATE — 1180 people, BUS_002 via FR_12 → Nimati School (ETA 35 min)' },
  { time: new Date().toISOString(), level: 'INFO', message: '🚤 Garamur: WATER ROUTE — 890 people, BOAT_001 via river → Jorhat Hall (ETA 55 min)' },
]

export default function useEvacuationPlan(demoMode = false, scenarioId = 'majuli_demo') {
  const [plan, setPlan] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchPlan = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(API.evacPlan(scenarioId))
      setPlan(data)
    } catch (err) {
      if (demoMode) {
        setPlan(DEMO_PLAN)
      } else {
        setError(err.message)
      }
    }
    setLoading(false)
  }, [scenarioId, demoMode])

  const fetchNotifications = useCallback(async () => {
    try {
      const { data } = await axios.get(API.evacNotify)
      setNotifications(data.notifications || [])
    } catch {
      if (demoMode) setNotifications(DEMO_NOTIFICATIONS)
    }
  }, [demoMode])

  const triggerDemo = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await axios.post(API.evacDemo)
      setPlan(data.plan || data)
      setNotifications(data.notifications || [])
    } catch {
      setPlan(DEMO_PLAN)
      setNotifications(DEMO_NOTIFICATIONS)
    }
    setLoading(false)
  }, [])

  const recompute = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await axios.post(API.evacCompute, { scenario_id: scenarioId })
      setPlan(data)
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }, [scenarioId])

  useEffect(() => {
    fetchPlan()
    fetchNotifications()
  }, [fetchPlan, fetchNotifications])

  return {
    plan,
    notifications,
    loading,
    error,
    triggerDemo,
    recompute,
    refetch: fetchPlan,
  }
}
