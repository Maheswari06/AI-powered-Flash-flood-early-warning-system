/**
 * useSSEUpdates — Server-Sent Events hook for real-time prediction updates.
 *
 * Connects to the SSE endpoint when alert level >= WATCH.
 * Falls back to polling (30s) when SSE is unavailable or alert is NORMAL.
 *
 * Usage:
 *   const { predictions, alertLevel, connected } = useSSEUpdates(basinId)
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || ''
const SSE_URL = `${API_BASE}/api/predictions/stream`
const POLL_URL = `${API_BASE}/api/predictions/latest`
const POLL_INTERVAL = 30_000
const SSE_LEVELS = new Set(['WATCH', 'WARNING', 'DANGER', 'EMERGENCY'])

export default function useSSEUpdates(basinId = 'brahmaputra') {
  const [predictions, setPredictions] = useState([])
  const [alertLevel, setAlertLevel]   = useState('NORMAL')
  const [connected, setConnected]     = useState(false)
  const [error, setError]             = useState(null)
  const eventSourceRef = useRef(null)
  const pollTimerRef   = useRef(null)
  const basinRef       = useRef(basinId)

  basinRef.current = basinId

  /* ── Process incoming data ───────────────────────────── */
  const processData = useCallback((data) => {
    const items = data.predictions || data.alerts || []
    setPredictions(items)

    // Determine max alert level
    const levels = ['NORMAL', 'WATCH', 'WARNING', 'DANGER', 'EMERGENCY']
    let maxIdx = 0
    items.forEach((p) => {
      const idx = levels.indexOf(p.alert_level || 'NORMAL')
      if (idx > maxIdx) maxIdx = idx
    })
    setAlertLevel(levels[maxIdx])
    setError(null)
  }, [])

  /* ── Polling fallback ────────────────────────────────── */
  const poll = useCallback(async () => {
    try {
      const { data } = await axios.get(POLL_URL, {
        params: { basin: basinRef.current },
        timeout: 10_000,
      })
      processData(data)
    } catch (err) {
      setError(err.message)
    }
  }, [processData])

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return
    poll() // immediate first fetch
    pollTimerRef.current = setInterval(poll, POLL_INTERVAL)
  }, [poll])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  /* ── SSE connection ──────────────────────────────────── */
  const connectSSE = useCallback(() => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    const url = `${SSE_URL}?basin=${basinRef.current}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      setError(null)
      stopPolling() // SSE takes over
    }

    es.addEventListener('prediction', (event) => {
      try {
        const data = JSON.parse(event.data)
        processData(data)
      } catch { /* ignore malformed */ }
    })

    es.addEventListener('alert', (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.alert_level) setAlertLevel(data.alert_level)
      } catch { /* ignore */ }
    })

    es.onerror = () => {
      setConnected(false)
      es.close()
      eventSourceRef.current = null
      // Fall back to polling
      startPolling()
    }
  }, [processData, stopPolling, startPolling])

  const disconnectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setConnected(false)
    }
  }, [])

  /* ── Main effect: switch between SSE and polling ─────── */
  useEffect(() => {
    // Start with polling to get initial data
    startPolling()

    return () => {
      stopPolling()
      disconnectSSE()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Upgrade to SSE when alert level is elevated
  useEffect(() => {
    if (SSE_LEVELS.has(alertLevel) && !eventSourceRef.current) {
      connectSSE()
    } else if (!SSE_LEVELS.has(alertLevel) && eventSourceRef.current) {
      disconnectSSE()
      startPolling()
    }
  }, [alertLevel, connectSSE, disconnectSSE, startPolling])

  // Reconnect when basin changes
  useEffect(() => {
    if (eventSourceRef.current) {
      disconnectSSE()
      connectSSE()
    } else {
      stopPolling()
      startPolling()
    }
  }, [basinId]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    predictions,
    alertLevel,
    connected,
    error,
    refresh: poll,
  }
}
