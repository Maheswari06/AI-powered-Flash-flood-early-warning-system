/**
 * VillageSelector — Search & select a village/station for monitoring.
 * Fetches available villages from the API and persists selection to IDB.
 */
import React, { useState, useEffect, useMemo } from 'react';
import { fetchVillages } from '../api';

const BASINS = [
  { id: 'brahmaputra', label: 'Brahmaputra Basin' },
  { id: 'beas',        label: 'Beas Basin' },
  { id: 'godavari',    label: 'Godavari Basin' },
];

export default function VillageSelector({ onSelect }) {
  const [basin, setBasin]       = useState('brahmaputra');
  const [villages, setVillages] = useState([]);
  const [search, setSearch]     = useState('');
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchVillages(basin)
      .then((data) => {
        setVillages(Array.isArray(data) ? data : data.villages || []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [basin]);

  const filtered = useMemo(() => {
    if (!search.trim()) return villages;
    const q = search.toLowerCase();
    return villages.filter(
      (v) =>
        v.name?.toLowerCase().includes(q) ||
        v.district?.toLowerCase().includes(q) ||
        v.id?.toLowerCase().includes(q),
    );
  }, [villages, search]);

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="bg-argus-card border-b border-argus-border px-4 py-3">
        <h1 className="text-lg font-bold text-argus-accent">Select Village</h1>
        <p className="text-xs text-argus-muted mt-0.5">
          Choose the village you're monitoring
        </p>
      </header>

      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        {/* Basin pills */}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {BASINS.map((b) => (
            <button
              key={b.id}
              onClick={() => setBasin(b.id)}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                basin === b.id
                  ? 'bg-argus-accent text-white'
                  : 'bg-argus-card text-argus-muted border border-argus-border'
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative">
          <svg className="absolute left-3 top-2.5 w-4 h-4 text-argus-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search village or district…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-argus-card border border-argus-border text-sm text-argus-text placeholder:text-argus-muted focus:outline-none focus:ring-2 focus:ring-argus-accent"
          />
        </div>

        {/* Loading / Error */}
        {loading && (
          <div className="flex justify-center py-8">
            <div className="w-8 h-8 rounded-full border-4 border-argus-border border-t-argus-accent animate-spin" />
          </div>
        )}
        {error && (
          <div className="bg-red-900/30 border border-red-600 rounded-lg p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Village list */}
        {!loading && !error && (
          <ul className="space-y-2">
            {filtered.map((v) => (
              <li key={v.id}>
                <button
                  onClick={() => onSelect(v)}
                  className="w-full text-left bg-argus-card hover:bg-argus-border/30 rounded-lg p-3 transition"
                >
                  <div className="font-semibold text-sm">{v.name}</div>
                  <div className="text-xs text-argus-muted mt-0.5">
                    {v.district && <span>{v.district} · </span>}
                    <span className="font-mono">{v.id}</span>
                  </div>
                </button>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="text-center text-argus-muted text-sm py-6">
                No villages found
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
