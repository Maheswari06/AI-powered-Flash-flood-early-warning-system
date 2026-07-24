/**
 * CodeEditor — YAML configuration editor for developer portal playground.
 *
 * Provides syntax-highlighted editing with real-time YAML validation.
 * Uses a simple textarea with validation overlay (no heavy dependency
 * like Monaco — keeps bundle small for the portal).
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { validateYaml, parseYaml } from '../utils/yaml';

const SAMPLE_CONFIG = `# ARGUS Basin Configuration
basin_id: my_custom_basin
name: Custom River Basin
region: South Asia

stations:
  - id: STATION_01
    name: Upstream Gauge
    lat: 26.15
    lon: 91.70
    type: cwc_gauge

  - id: STATION_02
    name: Downstream Gauge
    lat: 25.60
    lon: 89.90
    type: cwc_gauge

thresholds:
  warning_level_m: 8.5
  danger_level_m: 9.5
  emergency_level_m: 10.5

model:
  type: oracle_v2
  prediction_horizon_h: 72
  update_interval_min: 15
`;

export default function CodeEditor({ value, onChange, onValidation, readOnly = false }) {
  const [error, setError] = useState(null);
  const [lineCount, setLineCount] = useState(1);
  const textareaRef = useRef(null);
  const lineNumbersRef = useRef(null);

  const content = value ?? SAMPLE_CONFIG;

  const handleChange = useCallback(
    (e) => {
      const newValue = e.target.value;
      onChange?.(newValue);

      // Validate YAML on change
      const result = validateYaml(newValue);
      setError(result.error);
      onValidation?.(result);
    },
    [onChange, onValidation]
  );

  // Sync line numbers with content
  useEffect(() => {
    const lines = content.split('\n').length;
    setLineCount(lines);
  }, [content]);

  // Sync scroll between line numbers and textarea
  const handleScroll = useCallback(() => {
    if (lineNumbersRef.current && textareaRef.current) {
      lineNumbersRef.current.scrollTop = textareaRef.current.scrollTop;
    }
  }, []);

  return (
    <div className="flex flex-col h-full border border-slate-600 rounded-lg overflow-hidden bg-slate-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-800 border-b border-slate-700">
        <span className="text-xs font-mono text-slate-400">basin-config.yaml</span>
        <div className="flex items-center gap-2">
          {error ? (
            <span className="text-xs text-red-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
              YAML Error
            </span>
          ) : (
            <span className="text-xs text-green-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Valid
            </span>
          )}
        </div>
      </div>

      {/* Editor area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Line numbers */}
        <div
          ref={lineNumbersRef}
          className="flex-shrink-0 w-12 bg-slate-800/50 text-right pr-2 pt-2 overflow-hidden select-none"
        >
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="text-xs leading-5 text-slate-500 font-mono">
              {i + 1}
            </div>
          ))}
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={content}
          onChange={handleChange}
          onScroll={handleScroll}
          readOnly={readOnly}
          spellCheck={false}
          className="flex-1 bg-transparent text-sm text-slate-100 font-mono leading-5 p-2 resize-none outline-none placeholder-slate-500"
          placeholder="Paste your basin YAML configuration here..."
        />
      </div>

      {/* Error display */}
      {error && (
        <div className="px-3 py-2 bg-red-900/30 border-t border-red-800/50 text-xs text-red-300 font-mono">
          {error}
        </div>
      )}
    </div>
  );
}
