/**
 * FloodLedger — Phase 2 enhanced blockchain dashboard.
 *
 * Full-screen: chain stats, payout cards, blockchain terminal,
 * integrity verification, and "SIMULATE FLOOD EVENT" demo.
 */

import { useState } from 'react'
import useLedger from '../hooks/useLedger'

function shortenHash(h) {
  if (!h || h.length < 12) return h || '—'
  return h.slice(0, 8) + '…' + h.slice(-6)
}

const EVENT_COLORS = {
  prediction: { bg: 'bg-blue-900/30', text: 'text-blue-400', icon: '📊' },
  alert: { bg: 'bg-amber-900/30', text: 'text-amber-400', icon: '⚠️' },
  evacuation: { bg: 'bg-red-900/30', text: 'text-red-400', icon: '🚨' },
  verification: { bg: 'bg-green-900/30', text: 'text-green-400', icon: '✓' },
  payout: { bg: 'bg-cyan-900/30', text: 'text-cyan-400', icon: '💰' },
}

const PAYOUT_STATUS = {
  EXECUTED: { bg: 'bg-green-900/40', text: 'text-green-400', label: 'EXECUTED' },
  PENDING: { bg: 'bg-amber-900/40', text: 'text-amber-400', label: 'PENDING' },
  FAILED: { bg: 'bg-red-900/40', text: 'text-red-400', label: 'FAILED' },
}

export default function FloodLedger({ demoMode = false, fullScreen = false }) {
  const { summary, chain, payouts, integrity, verifying, verifyChain, simulateFloodEvent } = useLedger(demoMode)
  const [expanded, setExpanded] = useState(true)
  const [showTerminal, setShowTerminal] = useState(false)
  const [simulating, setSimulating] = useState(false)

  const handleSimulate = async () => {
    setSimulating(true)
    await simulateFloodEvent('kullu_01')
    setTimeout(() => setSimulating(false), 1500)
  }

  // Compact overlay mode
  if (!fullScreen) {
    if (!expanded) {
      return (
        <button
          onClick={() => setExpanded(true)}
          className="bg-navy/90 border border-gray-700 text-cyan-400 text-xs font-mono px-3 py-2 rounded-lg hover:border-cyan-400 transition-colors"
        >
          LEDGER ▸
        </button>
      )
    }

    return (
      <div className="bg-navy/95 backdrop-blur-sm border border-gray-700 rounded-xl p-4 max-w-xs">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-display text-sm text-white tracking-wider">
            FLOOD<span className="text-cyan-400">LEDGER</span>
          </h3>
          <button onClick={() => setExpanded(false)} className="text-gray-500 text-xs hover:text-white">✕</button>
        </div>
        <div className="text-xs text-gray-400">
          {summary?.length || 0} blocks · {summary?.entries_24h || 0} entries/24h
        </div>
      </div>
    )
  }

  // ── Full-screen mode ──────────────────────────────────────────────
  return (
    <div className="flex-1 flex bg-navy">
      {/* Left panel — Stats + Payouts */}
      <div className="w-96 border-r border-gray-800 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-white tracking-wider text-sm">
              🔗 FLOOD<span className="text-cyan-400">LEDGER</span>
            </h2>
            <div className="flex gap-2">
              <button
                onClick={verifyChain}
                disabled={verifying}
                className={`text-[10px] font-mono px-2 py-1 rounded border transition-colors ${
                  verifying
                    ? 'border-yellow-600 text-yellow-400 animate-pulse'
                    : integrity === true
                      ? 'border-green-600 text-green-400'
                      : integrity === false
                        ? 'border-red-600 text-red-400'
                        : 'border-gray-600 text-gray-400 hover:border-cyan-500'
                }`}
              >
                {verifying ? '⟳ VERIFYING...' : integrity === true ? '✓ VALID' : integrity === false ? '✗ TAMPERED' : '⟳ VERIFY'}
              </button>
            </div>
          </div>

          {/* Chain stats grid */}
          {summary && (
            <div className="grid grid-cols-4 gap-2 mb-3">
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <div className="text-xl text-white font-mono font-bold">{summary.length}</div>
                <div className="text-[8px] text-gray-500 uppercase">Blocks</div>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <div className="text-xl text-cyan-400 font-mono font-bold">{summary.entries_24h}</div>
                <div className="text-[8px] text-gray-500 uppercase">24h Entries</div>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <div className="text-xl text-white font-mono font-bold">{summary.villages_tracked}</div>
                <div className="text-[8px] text-gray-500 uppercase">Villages</div>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <div className={`text-xl font-mono font-bold ${integrity ? 'text-green-400' : 'text-amber-400'}`}>
                  {integrity ? '✓' : '?'}
                </div>
                <div className="text-[8px] text-gray-500 uppercase">Integrity</div>
              </div>
            </div>
          )}

          {/* Simulate flood event button */}
          <button
            onClick={handleSimulate}
            disabled={simulating}
            className="w-full text-xs font-mono bg-red-900/20 text-red-400 border border-red-900/40 rounded-lg px-3 py-2 hover:bg-red-900/30 disabled:opacity-50 transition-colors"
          >
            {simulating ? '⟳ SIMULATING EVENT...' : '🌊 SIMULATE FLOOD EVENT'}
          </button>
        </div>

        {/* Payout cards */}
        <div className="p-3 border-b border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
            Smart Contract Payouts
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {payouts.map((p, i) => {
              const badge = PAYOUT_STATUS[p.status] || PAYOUT_STATUS.PENDING
              return (
                <div key={p.policy_id || i} className="bg-gray-800/30 border border-gray-700 rounded-lg p-2.5">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[10px] text-cyan-400 font-mono">{p.policy_id}</span>
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${badge.bg} ${badge.text}`}>
                      {badge.label}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-white font-mono">₹{(p.amount_inr || 0).toLocaleString()}</span>
                    <span className="text-[9px] text-gray-500">{p.village_id}</span>
                  </div>
                  <div className="text-[9px] text-gray-600 mt-0.5">
                    Trigger: {p.trigger}
                  </div>
                </div>
              )
            })}
            {payouts.length === 0 && (
              <div className="text-[10px] text-gray-600 text-center py-3">
                No payout records — simulate a flood event
              </div>
            )}
          </div>
        </div>

        {/* Recent blocks list */}
        <div className="flex-1 overflow-y-auto p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">Block Chain</div>
            <button
              onClick={() => setShowTerminal(!showTerminal)}
              className={`text-[9px] font-mono px-2 py-0.5 rounded border transition-colors ${
                showTerminal ? 'border-cyan-600 text-cyan-400' : 'border-gray-700 text-gray-500 hover:border-cyan-600'
              }`}
            >
              {'>'} TERMINAL
            </button>
          </div>
          <div className="space-y-1.5">
            {chain.map((block) => (
              <div key={block.block_number} className="bg-gray-800/30 rounded-lg px-3 py-2">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] text-cyan-400 font-mono font-bold">#{block.block_number}</span>
                  <span className="text-[9px] text-gray-600 font-mono">nonce: {block.nonce}</span>
                </div>
                <div className="text-[9px] text-gray-500 font-mono truncate mt-0.5">
                  {shortenHash(block.hash)}
                </div>
                <div className="flex gap-1 mt-1 flex-wrap">
                  {block.entries?.map((e, i) => {
                    const ec = EVENT_COLORS[e.event_type] || EVENT_COLORS.prediction
                    return (
                      <span key={i} className={`text-[8px] px-1.5 py-0.5 rounded ${ec.bg} ${ec.text}`}>
                        {ec.icon} {e.event_type}:{e.village_id}
                      </span>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel — Terminal or Info view */}
      <div className="flex-1 flex flex-col">
        {showTerminal ? (
          /* Blockchain terminal */
          <div className="flex-1 bg-black p-4 font-mono text-xs overflow-auto">
            <div className="text-green-400 mb-2">HYDRA FloodLedger Terminal v2.1</div>
            <div className="text-gray-600 mb-4">{'>'} chain status</div>
            {summary && (
              <>
                <div className="text-cyan-400">Chain ID: {summary.chain_id}</div>
                <div className="text-white">Length: {summary.length} blocks</div>
                <div className="text-white">Entries (24h): {summary.entries_24h}</div>
                <div className="text-white">Villages: {summary.villages_tracked}</div>
                <div className={`${integrity ? 'text-green-400' : 'text-amber-400'}`}>
                  Integrity: {integrity ? 'VERIFIED ✓' : 'UNVERIFIED'}
                </div>
                <div className="text-gray-500 mt-2">Hash: {summary.last_hash}</div>
              </>
            )}
            <div className="text-gray-600 mt-4">{'>'} list payouts</div>
            {payouts.map((p, i) => (
              <div key={i} className="text-gray-300">
                [{p.status}] {p.policy_id} → {p.village_id} → ₹{(p.amount_inr || 0).toLocaleString()} ({p.trigger})
              </div>
            ))}
            <div className="text-gray-600 mt-4">{'>'} last blocks</div>
            {chain.map((b) => (
              <div key={b.block_number} className="text-gray-400">
                #{b.block_number} | {shortenHash(b.hash)} | nonce:{b.nonce} | {b.entries?.length || 0} entries
              </div>
            ))}
            <div className="text-green-400 mt-2 animate-pulse">{'>'} _</div>
          </div>
        ) : (
          /* Info view */
          <div className="flex-1 flex items-center justify-center bg-gray-900/30">
            <div className="text-center max-w-md">
              <div className="text-6xl mb-4">🔗</div>
              <h3 className="text-lg text-white font-display tracking-wider mb-2">FloodLedger</h3>
              <p className="text-xs text-gray-500 leading-relaxed">
                Tamper-proof blockchain recording every prediction, alert, evacuation order,
                and insurance payout. Each block is cryptographically linked to its predecessor,
                ensuring auditability for NDMA/SDMA compliance.
              </p>
              <div className="mt-6 grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-2xl text-cyan-400 font-mono font-bold">{summary?.length || 0}</div>
                  <div className="text-[9px] text-gray-500 uppercase">Total Blocks</div>
                </div>
                <div>
                  <div className="text-2xl text-white font-mono font-bold">{summary?.entries_24h || 0}</div>
                  <div className="text-[9px] text-gray-500 uppercase">24h Activity</div>
                </div>
                <div>
                  <div className="text-2xl text-green-400 font-mono font-bold">{payouts.length}</div>
                  <div className="text-[9px] text-gray-500 uppercase">Payouts</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
