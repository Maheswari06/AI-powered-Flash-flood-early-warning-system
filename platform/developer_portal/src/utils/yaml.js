/**
 * YAML utilities for developer portal playground.
 *
 * Provides safe YAML parsing and validation using js-yaml.
 * Falls back to basic structural checks if js-yaml isn't available.
 */

let jsYaml = null;

/**
 * Lazily load js-yaml. Returns the module or null.
 */
async function loadJsYaml() {
  if (jsYaml) return jsYaml;
  try {
    jsYaml = await import('js-yaml');
    return jsYaml;
  } catch {
    return null;
  }
}

/**
 * Parse a YAML string into a JavaScript object.
 *
 * @param {string} yamlStr - Raw YAML text
 * @returns {{ data: object|null, error: string|null }}
 */
export function parseYaml(yamlStr) {
  if (!yamlStr || !yamlStr.trim()) {
    return { data: null, error: 'Empty configuration' };
  }

  // Try js-yaml if loaded
  if (jsYaml) {
    try {
      const data = jsYaml.load(yamlStr, { schema: jsYaml.DEFAULT_SCHEMA });
      return { data, error: null };
    } catch (e) {
      return {
        data: null,
        error: `Line ${e.mark?.line + 1 || '?'}: ${e.reason || e.message}`,
      };
    }
  }

  // Fallback: basic structural validation without js-yaml
  try {
    // Check for common YAML errors
    const lines = yamlStr.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Check for tabs (YAML uses spaces only)
      if (line.includes('\t')) {
        return { data: null, error: `Line ${i + 1}: Tabs not allowed in YAML, use spaces` };
      }
    }

    // Try JSON parse as fallback (valid JSON is valid YAML)
    try {
      const data = JSON.parse(yamlStr);
      return { data, error: null };
    } catch {
      // Not JSON — assume YAML is structurally OK for now
      // Build basic key-value structure from top-level keys
      const data = {};
      for (const line of lines) {
        const match = line.match(/^(\w[\w_]*):\s*(.+)?$/);
        if (match) {
          const [, key, val] = match;
          data[key] = val?.trim() || null;
        }
      }
      return { data, error: null };
    }
  } catch (e) {
    return { data: null, error: e.message };
  }
}

/**
 * Validate YAML structure for ARGUS basin configuration.
 *
 * @param {string} yamlStr - Raw YAML text
 * @returns {{ valid: boolean, error: string|null, data: object|null, warnings: string[] }}
 */
export function validateYaml(yamlStr) {
  const { data, error } = parseYaml(yamlStr);

  if (error) {
    return { valid: false, error, data: null, warnings: [] };
  }

  if (!data || typeof data !== 'object') {
    return { valid: false, error: 'Configuration must be a YAML mapping', data: null, warnings: [] };
  }

  const warnings = [];

  // Check required fields
  if (!data.basin_id) {
    warnings.push('Missing "basin_id" — required for deployment');
  }
  if (!data.stations || !Array.isArray(data.stations)) {
    warnings.push('Missing "stations" array — at least one station required');
  } else {
    // Validate station structure
    data.stations.forEach((station, i) => {
      if (!station.id) warnings.push(`Station ${i + 1}: missing "id"`);
      if (station.lat == null) warnings.push(`Station ${i + 1}: missing "lat"`);
      if (station.lon == null) warnings.push(`Station ${i + 1}: missing "lon"`);
    });
  }

  if (!data.thresholds) {
    warnings.push('Missing "thresholds" — recommend setting warning/danger/emergency levels');
  }

  return {
    valid: true,
    error: null,
    data,
    warnings,
  };
}

/**
 * Initialize js-yaml on import (non-blocking).
 */
loadJsYaml();
