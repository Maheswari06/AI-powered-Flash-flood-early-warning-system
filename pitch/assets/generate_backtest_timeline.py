#!/usr/bin/env python3
"""
ARGUS Phase 4 — Backtest Timeline Visualization
Himachal Pradesh Flash Flood, August 14–15, 2023
Official System vs. ARGUS Backtest

Produces a split horizontal timeline:
- Top row: Official system (grey, no alerts until T-8)
- Bottom row: ARGUS backtest (color-coded by alert level)

Visual metaphor: two rivers — one dead silent, one alive with signals.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import json
import os

# ── Configuration ──────────────────────────────────────────
BG_COLOR = '#050d1a'
GRID_COLOR = '#0f1f33'
TEXT_MUTED = '#6B7280'
TEXT_WHITE = '#E5E7EB'
OFFICIAL_COLOR = '#374151'
ARGUS_CYAN = '#00c9ff'
YELLOW = '#EAB308'
ORANGE = '#F97316'
RED = '#EF4444'
DARK_RED = '#DC2626'
WARNING_AMBER = '#F59E0B'


def generate_timeline_svg():
    """
    Produces backtest_timeline.svg and backtest_timeline.png
    """

    fig, ax = plt.subplots(figsize=(22, 8))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # ── Time axis setup ────────────────────────────────────
    time_min = -200
    time_max = 40

    # ── TOP ROW: Official System (flat grey, dead silent) ──
    official_y = 0.72

    # Draw dashed baseline for official system
    ax.plot([time_min + 15, time_max - 10], [official_y, official_y],
            color=OFFICIAL_COLOR, linewidth=2.5, linestyle='--', alpha=0.7, zorder=2)

    # Label
    ax.text(time_min + 5, official_y, 'OFFICIAL\nSYSTEM',
            color=TEXT_MUTED, fontsize=9, va='center', ha='right',
            fontweight='bold', fontfamily='monospace')

    # "NO ALERT" markers on official line
    no_alert_times = [-180, -120, -94, -78, -45]
    for t in no_alert_times:
        ax.plot(t, official_y, 'o', color=OFFICIAL_COLOR, markersize=10,
                markeredgecolor='#4B5563', markeredgewidth=1.5, zorder=4)
        ax.text(t, official_y + 0.055, 'NO ALERT', color='#4B5563',
                fontsize=6.5, ha='center', va='bottom', fontweight='bold',
                fontfamily='monospace')

    # T-8: Official first warning (too late)
    ax.plot(-8, official_y, 's', color=WARNING_AMBER, markersize=16,
            markeredgecolor='#D97706', markeredgewidth=2, zorder=5)
    ax.text(-8, official_y + 0.065, 'FIRST\nWARNING', color=WARNING_AMBER,
            fontsize=8, ha='center', fontweight='bold', fontfamily='monospace',
            path_effects=[pe.withStroke(linewidth=2, foreground=BG_COLOR)])

    # Small annotation for official warning
    ax.annotate('SMS sent.\nMost asleep.\nTowers failing.',
                xy=(-8, official_y - 0.03), xytext=(-8, official_y - 0.10),
                color='#9CA3AF', fontsize=6, ha='center', va='top',
                fontfamily='monospace',
                arrowprops=dict(arrowstyle='->', color='#4B5563', lw=0.8))

    # ── T=0 FLOOD LINE ────────────────────────────────────
    ax.axvline(x=0, color='#3B82F6', linewidth=4, linestyle='-', alpha=0.5, zorder=1)
    ax.axvline(x=0, color='#1D4ED8', linewidth=2, linestyle='-', alpha=0.9, zorder=2)

    # Flood hit annotation
    flood_box = dict(boxstyle='round,pad=0.5', facecolor='#1E3A5F', edgecolor='#3B82F6',
                     alpha=0.9, linewidth=1.5)
    ax.text(5, 0.50, '  FLOOD HITS  \n  4.7m peak  \n  71 lives lost  ',
            color='#93C5FD', fontsize=9, va='center', ha='left',
            fontweight='bold', fontfamily='monospace', bbox=flood_box,
            path_effects=[pe.withStroke(linewidth=1, foreground='#1E3A5F')])

    # ── BOTTOM ROW: ARGUS Backtest (alive with color) ─────
    argus_y = 0.28

    # Draw solid baseline for ARGUS
    ax.plot([time_min + 15, time_max - 10], [argus_y, argus_y],
            color=ARGUS_CYAN, linewidth=2.5, alpha=0.6, zorder=2)

    # Label
    ax.text(time_min + 5, argus_y, 'ARGUS\nBACKTEST',
            color=ARGUS_CYAN, fontsize=9, va='center', ha='right',
            fontweight='bold', fontfamily='monospace')

    # ARGUS events with rich annotations
    argus_events = [
        {
            'time': -180, 'score': 0.23, 'color': YELLOW,
            'status': 'ADVISORY',
            'label': 'Soil saturation\n81% above baseline',
            'sublabel': 'PINN + ERA5-Land'
        },
        {
            'time': -120, 'score': 0.61, 'color': ORANGE,
            'status': 'WATCH',
            'label': 'Runoff coeff 3.2×\nIntervene: Dam Gate 2→25%',
            'sublabel': 'Causal GNN'
        },
        {
            'time': -94, 'score': 0.79, 'color': ORANGE,
            'status': 'WARNING',
            'label': '4 citizen reports\nacoustic anomaly',
            'sublabel': 'CHORUS verified'
        },
        {
            'time': -78, 'score': 0.91, 'color': RED,
            'status': 'EMERGENCY',
            'label': 'Depth +2.1m  Vel +280%\nEVACUATION DISPATCHED',
            'sublabel': 'CV Gauging → RL Agent'
        },
        {
            'time': -45, 'score': 0.87, 'color': RED,
            'status': 'EVACUATING',
            'label': '67% complete\n2,340 people moved',
            'sublabel': 'RL Route Optimizer'
        },
        {
            'time': -8, 'score': 0.95, 'color': DARK_RED,
            'status': 'COMPLETE',
            'label': 'All evacuations done\n5,890 people safe',
            'sublabel': 'Shelters 78% occupied'
        },
        {
            'time': 0, 'score': 0.98, 'color': DARK_RED,
            'status': 'CONFIRMED',
            'label': 'SAR confirms polygon\n3 parametric payouts',
            'sublabel': 'FloodLedger'
        },
    ]

    # Draw ARGUS event markers and labels
    for i, ev in enumerate(argus_events):
        t = ev['time']
        size = 10 + ev['score'] * 14
        glow_size = size + 6

        # Glow effect
        ax.plot(t, argus_y, 'o', color=ev['color'], markersize=glow_size,
                alpha=0.2, zorder=3)
        # Main marker
        ax.plot(t, argus_y, 'o', color=ev['color'], markersize=size,
                markeredgecolor='white', markeredgewidth=0.5, alpha=0.9, zorder=5)

        # Status label above marker
        ax.text(t, argus_y + 0.05, ev['status'], color=ev['color'],
                fontsize=7, ha='center', va='bottom', fontweight='bold',
                fontfamily='monospace',
                path_effects=[pe.withStroke(linewidth=2, foreground=BG_COLOR)])

        # Detail label below marker
        ax.text(t, argus_y - 0.05, ev['label'], color=ev['color'],
                fontsize=5.5, ha='center', va='top', fontfamily='monospace',
                alpha=0.85,
                path_effects=[pe.withStroke(linewidth=1.5, foreground=BG_COLOR)])

        # Sublabel (data source)
        ax.text(t, argus_y - 0.13, ev['sublabel'], color=TEXT_MUTED,
                fontsize=5, ha='center', va='top', fontfamily='monospace',
                style='italic')

    # ── Risk score trend line ─────────────────────────────
    argus_times = [ev['time'] for ev in argus_events]
    argus_scores = [ev['score'] for ev in argus_events]
    score_y = [argus_y + s * 0.18 for s in argus_scores]

    # Smooth the line
    from scipy.interpolate import make_interp_spline
    try:
        t_smooth = np.linspace(min(argus_times), max(argus_times), 200)
        spl = make_interp_spline(argus_times, score_y, k=2)
        y_smooth = spl(t_smooth)
        ax.plot(t_smooth, y_smooth, color=ARGUS_CYAN, linewidth=1.2, alpha=0.35, zorder=2)
        ax.fill_between(t_smooth, argus_y, y_smooth, color=ARGUS_CYAN, alpha=0.05, zorder=1)
    except Exception:
        ax.plot(argus_times, score_y, color=ARGUS_CYAN, linewidth=1.2, alpha=0.35, zorder=2)

    # ── 70-minute lead time gap annotation ────────────────
    # Draw bracket between T-78 (ARGUS emergency) and T-8 (official warning)
    bracket_y = 0.53
    ax.annotate('', xy=(-78, bracket_y), xytext=(-8, bracket_y),
                arrowprops=dict(arrowstyle='<->', color=ARGUS_CYAN, lw=2, alpha=0.8))
    ax.text(-43, bracket_y + 0.03,
            '70-MINUTE LEAD TIME GAP',
            color=ARGUS_CYAN, fontsize=10, ha='center', va='bottom',
            fontweight='bold', fontfamily='monospace',
            path_effects=[pe.withStroke(linewidth=3, foreground=BG_COLOR)])
    ax.text(-43, bracket_y - 0.03,
            'Lives that could have been saved',
            color=ARGUS_CYAN, fontsize=8, ha='center', va='top',
            fontfamily='monospace', style='italic', alpha=0.7,
            path_effects=[pe.withStroke(linewidth=2, foreground=BG_COLOR)])

    # ── Shaded intervention window ────────────────────────
    ax.axvspan(-180, -8, alpha=0.03, color=ARGUS_CYAN, zorder=0)

    # ── Clock time labels along bottom ────────────────────
    clock_times = {
        -180: '20:00', -120: '21:00', -94: '21:26',
        -78: '21:42', -45: '22:15', -8: '22:52', 0: '23:00'
    }
    for t, label in clock_times.items():
        ax.text(t, 0.02, label, color=TEXT_MUTED, fontsize=6.5, ha='center',
                fontfamily='monospace', rotation=0)

    # ── Summary box ───────────────────────────────────────
    summary_text = (
        'OFFICIAL LEAD TIME:  8 min\n'
        'ARGUS LEAD TIME:    78 min\n'
        'LEAD TIME GAIN:    +70 min\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        'EST. LIVES SAVED:   40–47\n'
        'PEOPLE EVACUATED:   5,890\n'
        'DAMAGE REDUCTION:     34%'
    )
    summary_box = dict(boxstyle='round,pad=0.6', facecolor='#0a1628',
                       edgecolor=ARGUS_CYAN, alpha=0.95, linewidth=1.5)
    ax.text(30, 0.28, summary_text, color=ARGUS_CYAN, fontsize=7.5,
            va='center', ha='left', fontfamily='monospace',
            bbox=summary_box, linespacing=1.6)

    # ── Title ─────────────────────────────────────────────
    ax.set_title(
        'Himachal Pradesh Flash Flood — August 14, 2023\n'
        'Official System vs. ARGUS Backtest',
        color=TEXT_WHITE, fontsize=16, fontweight='bold', pad=20,
        fontfamily='sans-serif')

    # ── Axis styling ──────────────────────────────────────
    ax.set_xlim(time_min, time_max + 55)
    ax.set_ylim(-0.02, 1.0)
    ax.set_xlabel('Minutes Relative to Flood Impact (T=0)',
                  color=TEXT_MUTED, fontsize=10, fontfamily='monospace', labelpad=10)

    # Custom x-ticks
    tick_positions = [-180, -150, -120, -90, -60, -30, 0, 30]
    tick_labels = [f'T{t}' if t < 0 else (f'T=0' if t == 0 else f'T+{t}')
                   for t in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, fontsize=8, fontfamily='monospace')
    ax.tick_params(axis='x', colors=TEXT_MUTED, length=4)

    # Hide y-axis
    ax.set_yticks([])
    ax.tick_params(axis='y', left=False)

    # Spine styling
    for spine in ax.spines.values():
        spine.set_color('#1F2937')
        spine.set_linewidth(0.5)

    # ── Grid lines (subtle) ──────────────────────────────
    for t in [-180, -120, -60, 0]:
        ax.axvline(x=t, color=GRID_COLOR, linewidth=0.5, alpha=0.5, zorder=0)

    # ── Save ──────────────────────────────────────────────
    os.makedirs('pitch/assets', exist_ok=True)

    plt.tight_layout()
    plt.savefig('pitch/assets/backtest_timeline.svg', format='svg',
                facecolor=BG_COLOR, dpi=150, bbox_inches='tight')
    plt.savefig('pitch/assets/backtest_timeline.png', format='png',
                facecolor=BG_COLOR, dpi=200, bbox_inches='tight')
    plt.close()
    print("✅ Backtest timeline saved to pitch/assets/backtest_timeline.svg and .png")


if __name__ == "__main__":
    generate_timeline_svg()
