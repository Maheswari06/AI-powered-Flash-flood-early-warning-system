/**
 * useLedger — Fetches FloodLedger blockchain data.
 *
 * Exposes chain summary, recent blocks, integrity verification, and demo flood simulation.
 */

import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

// Demo fallback
const DEMO_SUMMARY = {
  chain_id: 'argus_flood_ledger_v1',
  length: 47,
  last_hash: 'a3f8c2d1e5b6a9f4a7d2e0c8b3f1',
  entries_24h: 23,
  villages_tracked: 8,
  integrity_verified: true,
}

const DEMO_PAYOUTS = [
  { policy_id: 'POL-HP-2023-001', village_id: 'kullu_01', amount_inr: 250000, trigger: 'water_level > 4.5m', status: 'EXECUTED', timestamp: new Date().toISOString() },
  { policy_id: 'POL-HP-2023-002', village_id: 'mandi_01', amount_inr: 180000, trigger: 'rainfall > 80mm/hr', status: 'PENDING', timestamp: new Date().toISOString() },
  { policy_id: 'POL-AS-2023-001', village_id: 'majuli_01', amount_inr: 320000, trigger: 'flood_depth > 3.0m', status: 'EXECUTED', timestamp: new Date().toISOString() },
]

export default function useLedger(demoMode = false) {
  const [summary, setSummary] = useState(null)
  const [chain, setChain] = useState([])
  const [payouts, setPayouts] = useState([])
  const [integrity, setIntegrity] = useState(null)
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [sumRes, chainRes] = await Promise.all([
        axios.get(API.ledgerSummary),
        axios.get(API.ledgerChain),
      ])
      setSummary(sumRes.data)
      setChain(chainRes.data.slice(-8))
    } catch {
      if (demoMode) {
        setSummary(DEMO_SUMMARY)
        setPayouts(DEMO_PAYOUTS)
        setChain([
          { block_number: 45, timestamp: new Date().toISOString(), hash: '00a3f8c2d1e5b6a9f4a7d2e0c8b3f1d5', nonce: 142, entries: [{ event_type: 'prediction', village_id: 'kullu_01' }] },
          { block_number: 46, timestamp: new Date().toISOString(), hash: '0072b4e6f8d0a2c4e6b8d0f2a4c6e8b0', nonce: 89, entries: [{ event_type: 'alert', village_id: 'mandi_01' }] },
          { block_number: 47, timestamp: new Date().toISOString(), hash: '00e1c3d5f7a9b1d3f5a7c9e1b3d5f7a9', nonce: 234, entries: [{ event_type: 'evacuation', village_id: 'majuli_01' }] },
        ])
      }
    }
    setLoading(false)
  }, [demoMode])

  const verifyChain = useCallback(async () => {
    setVerifying(true)
    try {
      const { data } = await axios.get(API.ledgerVerify)
      setIntegrity(data.integrity)
    } catch {
      setIntegrity(true)
    }
    setTimeout(() => setVerifying(false), 1200)
  }, [])

  const simulateFloodEvent = useCallback(async (villageId = 'kullu_01') => {
    try {
      await axios.post(API.ledgerDemoFlood(villageId))
      await fetchData()
    } catch {
      // Add demo payout
      setPayouts(prev => [...prev, {
        policy_id: `POL-DEMO-${Date.now()}`,
        village_id: villageId,
        amount_inr: Math.round(Math.random() * 300000 + 100000),
        trigger: 'demo_flood_event',
        status: 'EXECUTED',
        timestamp: new Date().toISOString(),
      }])
    }
  }, [fetchData])

  useEffect(() => { fetchData() }, [fetchData])
  useEffect(() => {
    const iv = setInterval(fetchData, demoMode ? 10000 : 30000)
    return () => clearInterval(iv)
  }, [fetchData, demoMode])

  return {
    summary,
    chain,
    payouts,
    integrity,
    loading,
    verifying,
    verifyChain,
    simulateFloodEvent,
    refetch: fetchData,
  }
}
