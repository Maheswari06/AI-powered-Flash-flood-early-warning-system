/**
 * ReportFlood — Crowd-sourced flood condition reporting (CHORUS).
 * Works offline: queues reports in IndexedDB for background sync.
 */
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { submitFloodReport } from '../api';

const SEVERITY_OPTIONS = [
  { value: 'minor',    label: 'Minor — ankle-deep',   color: 'bg-yellow-500' },
  { value: 'moderate', label: 'Moderate — knee-deep',  color: 'bg-orange-500' },
  { value: 'severe',   label: 'Severe — waist-deep',   color: 'bg-red-500' },
  { value: 'extreme',  label: 'Extreme — above waist', color: 'bg-red-800' },
];

export default function ReportFlood({ village, online }) {
  const [severity, setSeverity] = useState('');
  const [description, setDescription] = useState('');
  const [photo, setPhoto]       = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);

  const handlePhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPhoto(reader.result); // base64
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!severity) return;

    setSubmitting(true);
    setError(null);
    setResult(null);

    const report = {
      village_id: village.id,
      village_name: village.name,
      severity,
      description: description.trim(),
      photo: photo || null,
      timestamp: new Date().toISOString(),
      coordinates: null,
    };

    // Try to get GPS coordinates
    if ('geolocation' in navigator) {
      try {
        const pos = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 5000 }),
        );
        report.coordinates = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        };
      } catch { /* GPS optional */ }
    }

    try {
      const res = await submitFloodReport(report);
      setResult(res);
      // Reset form on success
      setSeverity('');
      setDescription('');
      setPhoto(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="bg-argus-card border-b border-argus-border px-4 py-3 flex items-center gap-3">
        <Link to="/" className="text-argus-accent">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div>
          <h1 className="text-lg font-bold">Report Flood</h1>
          <p className="text-xs text-argus-muted">{village.name}</p>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="flex-1 p-4 space-y-4 overflow-y-auto">
        {/* Offline notice */}
        {!online && (
          <div className="bg-argus-orange/20 border border-argus-orange rounded-lg p-2 text-xs text-argus-orange">
            You're offline — report will be queued and sent automatically when reconnected.
          </div>
        )}

        {/* Severity */}
        <fieldset>
          <legend className="text-sm font-semibold text-argus-muted mb-2">Water Level *</legend>
          <div className="grid grid-cols-2 gap-2">
            {SEVERITY_OPTIONS.map((opt) => (
              <button
                type="button"
                key={opt.value}
                onClick={() => setSeverity(opt.value)}
                className={`rounded-lg p-3 text-sm font-semibold text-left transition border-2 ${
                  severity === opt.value
                    ? `${opt.color} text-white border-transparent`
                    : 'bg-argus-card text-argus-text border-argus-border'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Description */}
        <div>
          <label className="text-sm font-semibold text-argus-muted block mb-1">
            Description (optional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Road blocked, bridge submerged, etc."
            className="w-full rounded-lg bg-argus-card border border-argus-border p-3 text-sm text-argus-text placeholder:text-argus-muted focus:outline-none focus:ring-2 focus:ring-argus-accent resize-none"
          />
        </div>

        {/* Photo */}
        <div>
          <label className="text-sm font-semibold text-argus-muted block mb-1">Photo</label>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handlePhoto}
            className="block w-full text-sm text-argus-muted file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-argus-accent file:text-white"
          />
          {photo && (
            <img src={photo} alt="Preview" className="mt-2 rounded-lg max-h-40 object-cover" />
          )}
        </div>

        {/* Result */}
        {result && (
          <div className={`rounded-lg p-3 text-sm ${result.queued ? 'bg-yellow-900/30 text-yellow-300' : 'bg-green-900/30 text-green-300'}`}>
            {result.queued ? '📦 Report queued — will send when online' : '✅ Report submitted successfully'}
          </div>
        )}
        {error && (
          <div className="bg-red-900/30 border border-red-600 rounded-lg p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={!severity || submitting}
          className="w-full py-3 rounded-xl bg-argus-accent text-white font-bold text-sm disabled:opacity-40 transition"
        >
          {submitting ? 'Submitting…' : 'Submit Report'}
        </button>
      </form>
    </div>
  );
}
