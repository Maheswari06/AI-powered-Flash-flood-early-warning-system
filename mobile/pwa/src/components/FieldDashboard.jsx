/**
 * FieldDashboard — Main PWA screen for field officers.
 * Shows current alert level, SHAP explanations, risk score,
 * evacuation link, and crowd-source report button.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { fetchRiskData, fetchExplanation } from '../api';

const ALERT_STYLES = {
  NORMAL:    { bg: 'bg-green-600',  text: 'All Clear',         pulse: false },
  WATCH:     { bg: 'bg-yellow-500', text: 'Watch',             pulse: false },
  WARNING:   { bg: 'bg-orange-500', text: 'Warning',           pulse: true  },
  DANGER:    { bg: 'bg-red-600',    text: 'Danger',            pulse: true  },
  EMERGENCY: { bg: 'bg-red-800',    text: 'EMERGENCY — Evacuate', pulse: true },
};

const POLL_INTERVAL = 60_000; // 60 s

export default function FieldDashboard({ village, online, onChangeVillage }) {
  const [risk, setRisk]             = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const loadRisk = useCallback(async () => {
    try {
      const data = await fetchRiskData(village.id);
      setRisk(data);
      setLastUpdated(new Date());
      setError(null);

      // Auto-fetch SHAP explanation when elevated alert
      if (data.alert_level && data.alert_level !== 'NORMAL') {
        const stationId = data.predictions?.[0]?.station_id;
        if (stationId) {
          try {
            const exp = await fetchExplanation(stationId);
            setExplanation(exp);
          } catch { /* non-critical */ }
        }
      } else {
        setExplanation(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [village.id]);

  // Initial + periodic fetch
  useEffect(() => {
    loadRisk();
    const id = setInterval(loadRisk, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [loadRisk]);

  const alertLevel = risk?.alert_level || 'NORMAL';
  const style = ALERT_STYLES[alertLevel] || ALERT_STYLES.NORMAL;
  const riskScore = risk?.predictions?.[0]?.risk_score;
  const fromCache = risk?.fromCache;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="w-10 h-10 rounded-full border-4 border-argus-border border-t-argus-accent animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* ── Alert Banner ───────────────────────────────── */}
      <header className={`${style.bg} ${style.pulse ? 'animate-pulse' : ''} text-white px-4 py-3`}>
        <div className="flex items-center justify-between">
          <span className="text-lg font-bold tracking-wide">{style.text}</span>
          {fromCache && (
            <span className="text-xs bg-white/20 rounded px-2 py-0.5">cached</span>
          )}
        </div>
        <p className="text-xs opacity-90 mt-0.5">{village.name}</p>
      </header>

      <main className="flex-1 p-4 space-y-4 overflow-y-auto">
        {/* ── Risk Score Card ──────────────────────────── */}
        <section className="bg-argus-card rounded-xl p-4 shadow">
          <h2 className="text-sm text-argus-muted mb-1">Flood Risk Score</h2>
          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold">
              {riskScore !== undefined ? `${(riskScore * 100).toFixed(0)}%` : '—'}
            </span>
            <span className="text-xs text-argus-muted mb-1">
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : ''}
            </span>
          </div>

          {/* Mini bar */}
          {riskScore !== undefined && (
            <div className="mt-2 h-2 rounded-full bg-argus-border overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ${style.bg}`}
                style={{ width: `${Math.min(riskScore * 100, 100)}%` }}
              />
            </div>
          )}
        </section>

        {/* ── SHAP Explanation ("Why this alert?") ─────── */}
        {explanation && (
          <section className="bg-argus-card rounded-xl p-4 shadow">
            <h2 className="text-sm font-semibold text-argus-accent mb-2">
              Why this alert?
            </h2>
            <ul className="space-y-1">
              {(explanation.features || []).slice(0, 5).map((f, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span className="text-argus-text truncate mr-2">{f.name}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    <div
                      className={`h-1.5 rounded ${f.impact >= 0 ? 'bg-red-400' : 'bg-blue-400'}`}
                      style={{ width: `${Math.min(Math.abs(f.impact) * 100, 80)}px` }}
                    />
                    <span className="text-xs text-argus-muted w-10 text-right">
                      {f.impact >= 0 ? '+' : ''}{(f.impact * 100).toFixed(0)}%
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-xs text-argus-muted mt-2">
              Top factors from ARGUS SHAP explainability engine
            </p>
          </section>
        )}

        {/* ── Key Predictions ─────────────────────────── */}
        {risk?.predictions?.length > 0 && (
          <section className="bg-argus-card rounded-xl p-4 shadow">
            <h2 className="text-sm text-argus-muted mb-2">Station Predictions</h2>
            <div className="space-y-2">
              {risk.predictions.slice(0, 4).map((p) => (
                <div key={p.station_id} className="flex items-center justify-between text-sm">
                  <span className="truncate mr-2">{p.station_id}</span>
                  <span className="font-mono text-argus-accent">
                    {p.predicted_level?.toFixed(2) ?? '—'} m
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Evacuation Quick Link ───────────────────── */}
        {alertLevel !== 'NORMAL' && (
          <Link
            to="/evacuation"
            className="block bg-argus-accent text-white rounded-xl p-4 text-center font-semibold shadow hover:brightness-110 transition"
          >
            View Evacuation Plan →
          </Link>
        )}

        {/* ── Error ──────────────────────────────────── */}
        {error && (
          <div className="bg-red-900/30 border border-red-600 rounded-lg p-3 text-sm text-red-300">
            {error}
          </div>
        )}
      </main>

      {/* ── Bottom Action Bar ─────────────────────────── */}
      <nav className="sticky bottom-0 bg-argus-card border-t border-argus-border px-4 py-2 flex items-center justify-around safe-bottom">
        <Link to="/report" className="flex flex-col items-center text-argus-accent text-xs gap-0.5">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Report
        </Link>
        <button onClick={onChangeVillage} className="flex flex-col items-center text-argus-muted text-xs gap-0.5">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 12.414a1.5 1.5 0 00-2.121 0l-4.243 4.243M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Village
        </button>
        <Link to="/notifications" className="flex flex-col items-center text-argus-muted text-xs gap-0.5">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0" />
          </svg>
          Alerts
        </Link>
      </nav>
    </div>
  );
}
