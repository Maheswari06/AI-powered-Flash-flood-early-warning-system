/**
 * EvacuationCard — Displays evacuation routes, shelters, and supply points.
 * Caches the plan in IndexedDB for offline access.
 */
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchEvacPlan } from '../api';

function StatusBadge({ fromCache }) {
  if (!fromCache) return null;
  return (
    <span className="text-xs bg-argus-orange/20 text-argus-orange rounded px-2 py-0.5">
      cached
    </span>
  );
}

export default function EvacuationCard({ village, online }) {
  const [plan, setPlan]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    setLoading(true);
    fetchEvacPlan(village.id)
      .then(setPlan)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [village.id]);

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="bg-argus-card border-b border-argus-border px-4 py-3 flex items-center gap-3">
        <Link to="/" className="text-argus-accent">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-bold">Evacuation Plan</h1>
          <p className="text-xs text-argus-muted">{village.name}</p>
        </div>
        {plan && <StatusBadge fromCache={plan.fromCache} />}
      </header>

      <main className="flex-1 p-4 space-y-4 overflow-y-auto">
        {loading && (
          <div className="flex justify-center py-12">
            <div className="w-10 h-10 rounded-full border-4 border-argus-border border-t-argus-accent animate-spin" />
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 border border-red-600 rounded-lg p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {plan && !loading && (
          <>
            {/* Routes */}
            <section className="bg-argus-card rounded-xl p-4 shadow">
              <h2 className="text-sm font-semibold text-argus-accent mb-2">
                Evacuation Routes
              </h2>
              {(plan.routes || []).length === 0 ? (
                <p className="text-sm text-argus-muted">No routes available</p>
              ) : (
                <ol className="space-y-2 list-decimal list-inside">
                  {plan.routes.map((route, i) => (
                    <li key={i} className="text-sm">
                      <span className="font-medium">{route.name || `Route ${i + 1}`}</span>
                      {route.distance && (
                        <span className="text-argus-muted ml-2">({route.distance})</span>
                      )}
                      {route.description && (
                        <p className="text-xs text-argus-muted ml-5 mt-0.5">{route.description}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>

            {/* Shelters */}
            <section className="bg-argus-card rounded-xl p-4 shadow">
              <h2 className="text-sm font-semibold text-argus-accent mb-2">
                Shelters & Relief Camps
              </h2>
              {(plan.shelters || []).length === 0 ? (
                <p className="text-sm text-argus-muted">No shelters listed</p>
              ) : (
                <ul className="space-y-3">
                  {plan.shelters.map((s, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <div className="w-8 h-8 shrink-0 rounded-full bg-argus-accent/20 flex items-center justify-center text-argus-accent text-xs font-bold">
                        {i + 1}
                      </div>
                      <div>
                        <div className="text-sm font-medium">{s.name}</div>
                        {s.capacity && (
                          <div className="text-xs text-argus-muted">
                            Capacity: {s.capacity} people
                          </div>
                        )}
                        {s.contact && (
                          <a href={`tel:${s.contact}`} className="text-xs text-argus-accent underline">
                            {s.contact}
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Emergency contacts */}
            <section className="bg-argus-card rounded-xl p-4 shadow">
              <h2 className="text-sm font-semibold text-argus-accent mb-2">
                Emergency Contacts
              </h2>
              <div className="space-y-2">
                {[
                  { label: 'NDRF Helpline', number: '011-24363260' },
                  { label: 'SDMA Control Room', number: '1070' },
                  { label: 'District EOC', number: plan.eoc_number || '112' },
                ].map((c) => (
                  <a
                    key={c.number}
                    href={`tel:${c.number}`}
                    className="flex items-center justify-between bg-argus-border/20 rounded-lg p-3"
                  >
                    <span className="text-sm">{c.label}</span>
                    <span className="text-sm font-mono text-argus-accent">{c.number}</span>
                  </a>
                ))}
              </div>
            </section>

            {/* Last updated */}
            {plan.updated_at && (
              <p className="text-xs text-argus-muted text-center">
                Last updated: {new Date(plan.updated_at).toLocaleString()}
              </p>
            )}
          </>
        )}
      </main>
    </div>
  );
}
