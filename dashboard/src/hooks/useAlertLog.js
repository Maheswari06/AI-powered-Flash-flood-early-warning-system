import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import API from '../config/api'

const ALERT_API = import.meta.env.VITE_ALERT_API || ''
const POLL_INTERVAL = 10000 // 10 seconds

/**
 * Generate demo alert log entries that accumulate as risk rises.
 */
let demoAlertIdx = 0
const demoAlerts = []

function generateDemoAlerts() {
  demoAlertIdx++
  if (demoAlertIdx % 3 === 0 && demoAlerts.length < 30) {
    const levels = ['ADVISORY', 'ADVISORY', 'WATCH', 'WATCH', 'WARNING', 'WARNING', 'EMERGENCY']
    const villages = ['VIL-HP-MANDI', 'VIL-AS-MAJULI', 'VIL-HP-KULLU', 'VIL-AS-JORHAT', 'VIL-HP-MANALI']
    const level = levels[Math.min(Math.floor(demoAlertIdx / 5), levels.length - 1)]
    const villageId = villages[demoAlertIdx % villages.length]

    demoAlerts.unshift({
      id: `demo-${demoAlertIdx}`,
      village_id: villageId,
      village_name: villageId.replace('VIL-HP-', '').replace('VIL-AS-', ''),
      alert_level: level,
      risk_score: 0.3 + Math.random() * 0.6,
      timestamp: new Date().toISOString(),
      message: `${level} alert triggered for ${villageId.split('-').pop()}`,
      acknowledged: false,
    })
  }
  return [...demoAlerts]
}

/**
 * Hook that polls the alert log API.
 *
 * @param {boolean} demoMode
 * @returns {{ alerts, loading, error }}
 */
export default function useAlertLog(demoMode = false) {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const firstLoad = useRef(true)

  const fetchAlerts = useCallback(async () => {
    if (demoMode) {
      setAlerts(generateDemoAlerts())
      setLoading(false)
      setError(null)
      firstLoad.current = false
      return
    }

    try {
      const resp = await axios.get(API.alertLog, {
        timeout: 5000,
      })
      const data = Array.isArray(resp.data) ? resp.data : resp.data.alerts || []
      setAlerts(data)
      setError(null)
    } catch (err) {
      // Graceful fallback — keep last known alerts
      if (firstLoad.current) setAlerts([])
      setError(err.message)
    } finally {
      setLoading(false)
      firstLoad.current = false
    }
  }, [demoMode])

  useEffect(() => {
    if (demoMode) {
      demoAlertIdx = 0
      demoAlerts.length = 0
    }
  }, [demoMode])

  useEffect(() => {
    fetchAlerts()
    const timer = setInterval(fetchAlerts, demoMode ? 5000 : POLL_INTERVAL)
    return () => clearInterval(timer)
  }, [fetchAlerts, demoMode])

  return { alerts, loading, error }
}
