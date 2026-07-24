/**
 * ARGUS Alert Widget — Embeddable for NDMA / Government Portals
 *
 * Usage:
 *   <div id="argus-widget"></div>
 *   <script
 *     src="https://argus.hydra.gov.in/widget/argus-widget.js"
 *     data-basin="brahmaputra"
 *     data-district="kamrup"
 *     data-theme="light"
 *     data-api="https://argus.hydra.gov.in/api"
 *   ></script>
 *
 * No dependencies — vanilla JS, self-contained styling.
 */
(function () {
  'use strict';

  /* ── Configuration from script tag attributes ─────────── */
  const scriptTag = document.currentScript;
  const CONFIG = {
    basin:   scriptTag?.getAttribute('data-basin')   || 'brahmaputra',
    district: scriptTag?.getAttribute('data-district') || '',
    theme:   scriptTag?.getAttribute('data-theme')    || 'dark',
    apiBase: scriptTag?.getAttribute('data-api')      || '/api',
    target:  scriptTag?.getAttribute('data-target')   || 'argus-widget',
    refresh: parseInt(scriptTag?.getAttribute('data-refresh') || '60', 10),
  };

  const ALERT_COLORS = {
    NORMAL:    { bg: '#16a34a', text: '#ffffff', label: 'Normal' },
    WATCH:     { bg: '#eab308', text: '#000000', label: 'Watch' },
    WARNING:   { bg: '#f97316', text: '#ffffff', label: 'Warning' },
    DANGER:    { bg: '#dc2626', text: '#ffffff', label: 'Danger' },
    EMERGENCY: { bg: '#991b1b', text: '#ffffff', label: 'EMERGENCY' },
  };

  const THEMES = {
    dark: {
      bg: '#0f172a', card: '#1e293b', text: '#e2e8f0',
      muted: '#94a3b8', border: '#334155', accent: '#38bdf8',
    },
    light: {
      bg: '#f8fafc', card: '#ffffff', text: '#1e293b',
      muted: '#64748b', border: '#e2e8f0', accent: '#0284c7',
    },
  };

  /* ── Inject scoped CSS ────────────────────────────────── */
  function injectStyles(theme) {
    const t = THEMES[theme] || THEMES.dark;
    const css = `
      .argus-w { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: ${t.bg}; color: ${t.text}; border: 1px solid ${t.border}; border-radius: 12px; overflow: hidden; max-width: 400px; min-width: 280px; }
      .argus-w * { box-sizing: border-box; margin: 0; padding: 0; }
      .argus-w-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid ${t.border}; }
      .argus-w-logo { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; color: ${t.accent}; }
      .argus-w-logo svg { width: 20px; height: 20px; }
      .argus-w-badge { font-size: 10px; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
      .argus-w-body { padding: 16px; }
      .argus-w-alert { border-radius: 8px; padding: 12px; margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
      .argus-w-alert-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
      .argus-w-alert-info { flex: 1; min-width: 0; }
      .argus-w-alert-station { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .argus-w-alert-detail { font-size: 11px; color: ${t.muted}; margin-top: 2px; }
      .argus-w-empty { text-align: center; padding: 24px; color: ${t.muted}; font-size: 13px; }
      .argus-w-footer { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-top: 1px solid ${t.border}; font-size: 11px; color: ${t.muted}; }
      .argus-w-footer a { color: ${t.accent}; text-decoration: none; }
      .argus-w-footer a:hover { text-decoration: underline; }
      .argus-w-loading { display: flex; justify-content: center; padding: 32px; }
      .argus-w-spinner { width: 24px; height: 24px; border: 3px solid ${t.border}; border-top-color: ${t.accent}; border-radius: 50%; animation: argus-spin 0.8s linear infinite; }
      @keyframes argus-spin { to { transform: rotate(360deg); } }
      .argus-w-error { background: #7f1d1d33; border: 1px solid #dc2626; border-radius: 8px; padding: 10px; color: #fca5a5; font-size: 12px; text-align: center; }
      .argus-w-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
      .argus-w-stat { background: ${t.card}; border: 1px solid ${t.border}; border-radius: 8px; padding: 10px; text-align: center; }
      .argus-w-stat-val { font-size: 20px; font-weight: 700; color: ${t.text}; }
      .argus-w-stat-label { font-size: 10px; color: ${t.muted}; margin-top: 2px; text-transform: uppercase; }
    `;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ── Fetch predictions ────────────────────────────────── */
  async function fetchAlerts() {
    const params = new URLSearchParams();
    if (CONFIG.basin) params.set('basin', CONFIG.basin);
    if (CONFIG.district) params.set('district', CONFIG.district);

    const res = await fetch(`${CONFIG.apiBase}/predictions/latest?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  /* ── Render widget ────────────────────────────────────── */
  function render(container, data) {
    const t = THEMES[CONFIG.theme] || THEMES.dark;
    const alerts = (data.predictions || data.alerts || []).slice(0, 5);

    // Compute summary
    const counts = { elevated: 0, stations: alerts.length, maxLevel: 'NORMAL' };
    const levelOrder = ['NORMAL', 'WATCH', 'WARNING', 'DANGER', 'EMERGENCY'];
    alerts.forEach((a) => {
      const lvl = a.alert_level || 'NORMAL';
      if (lvl !== 'NORMAL') counts.elevated++;
      if (levelOrder.indexOf(lvl) > levelOrder.indexOf(counts.maxLevel)) {
        counts.maxLevel = lvl;
      }
    });

    const alertStyle = ALERT_COLORS[counts.maxLevel] || ALERT_COLORS.NORMAL;
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    container.innerHTML = `
      <div class="argus-w">
        <div class="argus-w-header">
          <div class="argus-w-logo">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 19h20L12 2zm0 4l6.93 12H5.07L12 6z"/><circle cx="12" cy="16" r="1.5"/><rect x="11.25" y="10" width="1.5" height="4" rx="0.75"/></svg>
            ARGUS
          </div>
          <span class="argus-w-badge" style="background:${alertStyle.bg};color:${alertStyle.text}">${alertStyle.label}</span>
        </div>
        <div class="argus-w-body">
          <div class="argus-w-summary">
            <div class="argus-w-stat">
              <div class="argus-w-stat-val">${counts.stations}</div>
              <div class="argus-w-stat-label">Stations</div>
            </div>
            <div class="argus-w-stat">
              <div class="argus-w-stat-val" style="color:${counts.elevated > 0 ? '#ef4444' : '#22c55e'}">${counts.elevated}</div>
              <div class="argus-w-stat-label">Elevated</div>
            </div>
            <div class="argus-w-stat">
              <div class="argus-w-stat-val" style="color:${alertStyle.bg}">${alertStyle.label}</div>
              <div class="argus-w-stat-label">Max Level</div>
            </div>
          </div>
          ${alerts.length === 0
            ? '<div class="argus-w-empty">No active alerts for this region</div>'
            : alerts.map((a) => {
                const lvl = a.alert_level || 'NORMAL';
                const c = ALERT_COLORS[lvl] || ALERT_COLORS.NORMAL;
                return `<div class="argus-w-alert" style="background:${c.bg}20;border:1px solid ${c.bg}40">
                  <div class="argus-w-alert-dot" style="background:${c.bg}"></div>
                  <div class="argus-w-alert-info">
                    <div class="argus-w-alert-station">${a.station_id || a.station_name || 'Unknown'}</div>
                    <div class="argus-w-alert-detail">
                      Level: ${a.predicted_level?.toFixed(2) || '—'} m · Risk: ${a.risk_score ? (a.risk_score * 100).toFixed(0) + '%' : '—'}
                    </div>
                  </div>
                  <span class="argus-w-badge" style="background:${c.bg};color:${c.text}">${c.label}</span>
                </div>`;
              }).join('')
          }
        </div>
        <div class="argus-w-footer">
          <span>Updated ${now}</span>
          <a href="https://argus.hydra.gov.in" target="_blank" rel="noopener">ARGUS Dashboard ↗</a>
        </div>
      </div>
    `;
  }

  function renderLoading(container) {
    container.innerHTML = `<div class="argus-w"><div class="argus-w-loading"><div class="argus-w-spinner"></div></div></div>`;
  }

  function renderError(container, msg) {
    container.innerHTML = `<div class="argus-w"><div class="argus-w-body"><div class="argus-w-error">${msg}</div></div></div>`;
  }

  /* ── Bootstrap ────────────────────────────────────────── */
  async function init() {
    injectStyles(CONFIG.theme);

    const container = document.getElementById(CONFIG.target);
    if (!container) {
      console.error('[ARGUS Widget] Target element #' + CONFIG.target + ' not found');
      return;
    }

    async function refresh() {
      try {
        const data = await fetchAlerts();
        render(container, data);
      } catch (err) {
        renderError(container, 'Failed to load alerts: ' + err.message);
      }
    }

    renderLoading(container);
    await refresh();

    // Auto-refresh
    if (CONFIG.refresh > 0) {
      setInterval(refresh, CONFIG.refresh * 1000);
    }
  }

  // Run when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
