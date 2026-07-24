/**
 * BasinPreviewCard — Visual preview of a parsed basin configuration.
 *
 * Shows station locations, thresholds, and model settings
 * extracted from the YAML config in the playground editor.
 */
import { useMemo } from 'react';

export default function BasinPreviewCard({ config }) {
  if (!config) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 text-center">
        <p className="text-slate-400 text-sm">
          Edit the YAML configuration to see a preview
        </p>
      </div>
    );
  }

  const stations = config.stations || [];
  const thresholds = config.thresholds || {};
  const model = config.model || {};

  const stationTypes = useMemo(() => {
    const counts = {};
    stations.forEach((s) => {
      const t = s.type || 'unknown';
      counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
  }, [stations]);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 bg-slate-800/80">
        <h3 className="text-sm font-semibold text-slate-100">
          {config.name || config.basin_id || 'Unnamed Basin'}
        </h3>
        <p className="text-xs text-slate-400 mt-0.5">
          {config.region || 'Region not specified'} · ID: {config.basin_id || '—'}
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-px bg-slate-700">
        <div className="bg-slate-800 px-3 py-2.5 text-center">
          <div className="text-lg font-bold text-sky-400">{stations.length}</div>
          <div className="text-xs text-slate-400">Stations</div>
        </div>
        <div className="bg-slate-800 px-3 py-2.5 text-center">
          <div className="text-lg font-bold text-amber-400">
            {thresholds.danger_level_m || '—'}
          </div>
          <div className="text-xs text-slate-400">Danger (m)</div>
        </div>
        <div className="bg-slate-800 px-3 py-2.5 text-center">
          <div className="text-lg font-bold text-emerald-400">
            {model.prediction_horizon_h || '—'}h
          </div>
          <div className="text-xs text-slate-400">Horizon</div>
        </div>
      </div>

      {/* Stations list */}
      <div className="p-3">
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Stations
        </h4>
        {stations.length === 0 ? (
          <p className="text-xs text-slate-500">No stations defined</p>
        ) : (
          <ul className="space-y-1.5">
            {stations.slice(0, 8).map((station, i) => (
              <li
                key={station.id || i}
                className="flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                  <span className="text-slate-200 font-mono">
                    {station.id || `Station ${i + 1}`}
                  </span>
                </div>
                <span className="text-slate-500">
                  {station.lat?.toFixed(2)}, {station.lon?.toFixed(2)}
                </span>
              </li>
            ))}
            {stations.length > 8 && (
              <li className="text-xs text-slate-500 pl-4">
                +{stations.length - 8} more stations
              </li>
            )}
          </ul>
        )}
      </div>

      {/* Station types */}
      {Object.keys(stationTypes).length > 0 && (
        <div className="px-3 pb-3">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(stationTypes).map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-700 text-xs text-slate-300"
              >
                {type}
                <span className="text-slate-500">×{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Model info */}
      {model.type && (
        <div className="px-3 pb-3 border-t border-slate-700 pt-2">
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
            Model
          </h4>
          <div className="text-xs text-slate-300 font-mono">
            {model.type} · every {model.update_interval_min || '?'}min
          </div>
        </div>
      )}

      {/* Thresholds */}
      {(thresholds.warning_level_m || thresholds.danger_level_m) && (
        <div className="px-3 pb-3 border-t border-slate-700 pt-2">
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
            Thresholds
          </h4>
          <div className="flex gap-3 text-xs">
            {thresholds.warning_level_m && (
              <span className="text-amber-300">
                ⚠ Warning: {thresholds.warning_level_m}m
              </span>
            )}
            {thresholds.danger_level_m && (
              <span className="text-orange-400">
                🔶 Danger: {thresholds.danger_level_m}m
              </span>
            )}
            {thresholds.emergency_level_m && (
              <span className="text-red-400">
                🚨 Emergency: {thresholds.emergency_level_m}m
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
