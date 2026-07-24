/**
 * useFederatedStatus — Fetches Federated Learning server status.
 *
 * Exposes FL round info, node participation, model accuracy, and ORACLE mode.
 */

import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import API from '../config/api'

const DEMO_STATUS = {
  mode: 'ORACLE',
  current_round: 7,
  total_rounds: 50,
  participating_nodes: 4,
  total_nodes: 6,
  global_accuracy: 0.847,
  convergence_rate: 0.92,
  last_aggregation: new Date().toISOString(),
  nodes: [
    { node_id: 'kullu_node', status: 'active', local_accuracy: 0.86, samples: 1240, last_heartbeat: new Date().toISOString() },
    { node_id: 'mandi_node', status: 'active', local_accuracy: 0.83, samples: 980, last_heartbeat: new Date().toISOString() },
    { node_id: 'majuli_node', status: 'active', local_accuracy: 0.89, samples: 1560, last_heartbeat: new Date().toISOString() },
    { node_id: 'dhemaji_node', status: 'active', local_accuracy: 0.81, samples: 720, last_heartbeat: new Date().toISOString() },
    { node_id: 'shimla_node', status: 'offline', local_accuracy: 0.78, samples: 450, last_heartbeat: new Date(Date.now() - 3600000).toISOString() },
    { node_id: 'sujanpur_node', status: 'syncing', local_accuracy: 0.80, samples: 600, last_heartbeat: new Date().toISOString() },
  ],
}

export default function useFederatedStatus(demoMode = false) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await axios.get(API.flStatus)
      setStatus(data)
    } catch {
      if (demoMode) setStatus(DEMO_STATUS)
    }
    setLoading(false)
  }, [demoMode])

  useEffect(() => { fetchStatus() }, [fetchStatus])
  useEffect(() => {
    const iv = setInterval(fetchStatus, demoMode ? 15000 : 60000)
    return () => clearInterval(iv)
  }, [fetchStatus, demoMode])

  return {
    status,
    loading,
    refetch: fetchStatus,
  }
}
