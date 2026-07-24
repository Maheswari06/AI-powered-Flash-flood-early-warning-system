#!/usr/bin/env python3
"""
ARGUS Phase 4 — Architecture Diagram Generator
Produces a clean, judge-legible system architecture SVG using matplotlib.

Fallback approach: hand-crafted diagram using matplotlib patches and arrows
(no external dependency on `diagrams` library or Graphviz).
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
import os

# ── Color Palette ──────────────────────────────────────────
BG = '#050d1a'
LAYER_BG = {
    'ingestion': '#0a1a2e',
    'processing': '#0a1a2e',
    'response': '#0a1a2e',
    'delivery': '#0a1a2e',
}
LAYER_BORDER = {
    'ingestion': '#00c9ff',
    'processing': '#a855f7',
    'response': '#f97316',
    'delivery': '#22c55e',
}
LAYER_TEXT = {
    'ingestion': '#00c9ff',
    'processing': '#a855f7',
    'response': '#f97316',
    'delivery': '#22c55e',
}
NODE_BG = '#0d2137'
NODE_BORDER = '#1e3a5f'
TEXT_WHITE = '#e5e7eb'
TEXT_MUTED = '#9ca3af'
ARROW_COLOR = '#374151'
KAFKA_COLOR = '#00c9ff'


def draw_node(ax, x, y, w, h, title, subtitle, color='#00c9ff'):
    """Draw a single service node."""
    rect = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle="round,pad=0.02",
        facecolor=NODE_BG, edgecolor=color,
        linewidth=1.5, alpha=0.95, zorder=3
    )
    ax.add_patch(rect)
    ax.text(x, y + 0.02, title, color=color, fontsize=7,
            ha='center', va='center', fontweight='bold', fontfamily='monospace',
            path_effects=[pe.withStroke(linewidth=1, foreground=NODE_BG)], zorder=4)
    ax.text(x, y - 0.04, subtitle, color=TEXT_MUTED, fontsize=5,
            ha='center', va='center', fontfamily='monospace', zorder=4)
    return (x, y)


def draw_layer_box(ax, x, y, w, h, title, color):
    """Draw a layer grouping box."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02",
        facecolor=LAYER_BG['ingestion'], edgecolor=color,
        linewidth=1.5, alpha=0.4, linestyle='--', zorder=1
    )
    ax.add_patch(rect)
    ax.text(x + w/2, y + h + 0.02, title, color=color, fontsize=8,
            ha='center', va='bottom', fontweight='bold', fontfamily='monospace',
            zorder=2)


def draw_arrow(ax, start, end, color=ARROW_COLOR, style='->', lw=1.2):
    """Draw a connecting arrow between nodes."""
    ax.annotate('', xy=end, xytext=start,
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                               connectionstyle='arc3,rad=0.1'),
                zorder=2)


def generate_architecture_diagram():
    fig, ax = plt.subplots(figsize=(24, 12))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_aspect('equal')
    ax.axis('off')

    # ── Title ──────────────────────────────────────────────
    ax.text(0.5, 1.00, 'ARGUS — System Architecture',
            color=TEXT_WHITE, fontsize=18, ha='center', va='top',
            fontweight='bold', fontfamily='sans-serif',
            path_effects=[pe.withStroke(linewidth=2, foreground=BG)])
    ax.text(0.5, 0.96, '12 Microservices · Apache Kafka · Causal AI · Offline-First Alert Delivery',
            color=TEXT_MUTED, fontsize=9, ha='center', va='top', fontfamily='monospace')

    # ══════════════════════════════════════════════════════
    # LAYER 1: DATA INGESTION (left column)
    # ══════════════════════════════════════════════════════
    layer1_color = LAYER_BORDER['ingestion']
    draw_layer_box(ax, 0.01, 0.12, 0.18, 0.75, 'DATA INGESTION', layer1_color)

    cctv = draw_node(ax, 0.10, 0.78, 0.14, 0.09, 'CCTV Feeds', 'RTSP streams', layer1_color)
    iot = draw_node(ax, 0.10, 0.64, 0.14, 0.09, 'IoT Gauges', 'CWC sensors', layer1_color)
    sat = draw_node(ax, 0.10, 0.50, 0.14, 0.09, 'Sentinel-1/2', 'SAR + optical', layer1_color)
    chorus_in = draw_node(ax, 0.10, 0.36, 0.14, 0.09, 'CHORUS', 'WhatsApp reports', layer1_color)
    weather = draw_node(ax, 0.10, 0.22, 0.14, 0.09, 'Weather APIs', 'IMD + ERA5', layer1_color)

    # ── Kafka Bus ──────────────────────────────────────────
    kafka_x = 0.26
    kafka_rect = FancyBboxPatch(
        (kafka_x - 0.025, 0.15), 0.05, 0.72,
        boxstyle="round,pad=0.01",
        facecolor='#001a33', edgecolor=KAFKA_COLOR,
        linewidth=2, alpha=0.8, zorder=3
    )
    ax.add_patch(kafka_rect)
    ax.text(kafka_x, 0.51, 'K\nA\nF\nK\nA', color=KAFKA_COLOR, fontsize=8,
            ha='center', va='center', fontweight='bold', fontfamily='monospace',
            rotation=0, linespacing=1.3, zorder=4)

    # Arrows: sources → Kafka
    for src in [cctv, iot, sat, chorus_in, weather]:
        draw_arrow(ax, (src[0] + 0.07, src[1]), (kafka_x - 0.025, src[1]),
                   color=layer1_color, lw=1.0)

    # ══════════════════════════════════════════════════════
    # LAYER 2: AI PROCESSING (center-left)
    # ══════════════════════════════════════════════════════
    layer2_color = LAYER_BORDER['processing']
    draw_layer_box(ax, 0.30, 0.12, 0.22, 0.75, 'AI PROCESSING', layer2_color)

    cv = draw_node(ax, 0.41, 0.78, 0.16, 0.09, 'CV Gauging', 'YOLO v11 + SAM2', layer2_color)
    pinn = draw_node(ax, 0.41, 0.64, 0.16, 0.09, 'PINN Mesh', '5000 virtual pts', layer2_color)
    feat = draw_node(ax, 0.41, 0.50, 0.16, 0.09, 'Feature Engine', 'Kalman + spatial', layer2_color)
    xgb = draw_node(ax, 0.41, 0.36, 0.16, 0.09, 'XGBoost Fast', '<10ms inference', layer2_color)
    tft = draw_node(ax, 0.41, 0.22, 0.16, 0.09, 'TFT Deep Track', '90-min horizon', layer2_color)

    # Arrows: Kafka → processing
    for proc in [cv, pinn, feat]:
        draw_arrow(ax, (kafka_x + 0.025, proc[1]), (proc[0] - 0.08, proc[1]),
                   color=KAFKA_COLOR, lw=1.0)

    # Internal processing flows
    draw_arrow(ax, (pinn[0], pinn[1] - 0.05), (feat[0], feat[1] + 0.05), color=layer2_color)
    draw_arrow(ax, (feat[0], feat[1] - 0.05), (xgb[0], xgb[1] + 0.05), color=layer2_color)
    draw_arrow(ax, (feat[0], feat[1] - 0.05), (tft[0], tft[1] + 0.05), color=layer2_color)

    # ══════════════════════════════════════════════════════
    # LAYER 3: DECISION ENGINE (center-right)
    # ══════════════════════════════════════════════════════
    layer3_color = LAYER_BORDER['response']
    draw_layer_box(ax, 0.55, 0.12, 0.22, 0.75, 'DECISION ENGINE', layer3_color)

    causal = draw_node(ax, 0.66, 0.75, 0.16, 0.10, 'Causal GNN', 'do-calculus\ninterventions', layer3_color)
    rl = draw_node(ax, 0.66, 0.58, 0.16, 0.09, 'RL Evacuation', 'PPO agent', layer3_color)
    mirror = draw_node(ax, 0.66, 0.44, 0.16, 0.09, 'MIRROR', 'counterfactual', layer3_color)
    ledger = draw_node(ax, 0.66, 0.30, 0.16, 0.09, 'FloodLedger', 'parametric oracle', layer3_color)
    federated = draw_node(ax, 0.66, 0.18, 0.16, 0.09, 'Federated', 'Flower FL server', layer3_color)

    # Arrows: processing → decision
    draw_arrow(ax, (xgb[0] + 0.08, xgb[1]), (causal[0] - 0.08, causal[1] - 0.03),
               color=layer2_color, lw=1.0)
    draw_arrow(ax, (tft[0] + 0.08, tft[1]), (causal[0] - 0.08, causal[1] - 0.05),
               color=layer2_color, lw=1.0)

    # Internal decision flows
    draw_arrow(ax, (causal[0], causal[1] - 0.06), (rl[0], rl[1] + 0.05), color=layer3_color)
    draw_arrow(ax, (causal[0], causal[1] - 0.06), (mirror[0], mirror[1] + 0.05), color=layer3_color)
    draw_arrow(ax, (causal[0], causal[1] - 0.06), (ledger[0], ledger[1] + 0.05), color=layer3_color)

    # ══════════════════════════════════════════════════════
    # LAYER 4: ALERT DELIVERY (right column)
    # ══════════════════════════════════════════════════════
    layer4_color = LAYER_BORDER['delivery']
    draw_layer_box(ax, 0.80, 0.12, 0.18, 0.75, 'ALERT DELIVERY', layer4_color)

    acn = draw_node(ax, 0.89, 0.75, 0.14, 0.09, 'ACN Node', 'ORACLE TinyML', layer4_color)
    lora = draw_node(ax, 0.89, 0.60, 0.14, 0.09, 'LoRaWAN', 'siren mesh 20km', layer4_color)
    cell = draw_node(ax, 0.89, 0.46, 0.14, 0.09, 'Cell Broadcast', 'all phones', layer4_color)
    whatsapp = draw_node(ax, 0.89, 0.32, 0.14, 0.09, 'WhatsApp IVR', 'audio in local lang', layer4_color)
    api = draw_node(ax, 0.89, 0.18, 0.14, 0.09, 'API Gateway', 'REST + WebSocket', layer4_color)

    # Arrows: decision → delivery
    draw_arrow(ax, (rl[0] + 0.08, rl[1]), (acn[0] - 0.07, acn[1]), color=layer3_color, lw=1.0)

    # ACN → downstream alerts
    draw_arrow(ax, (acn[0], acn[1] - 0.05), (lora[0], lora[1] + 0.05), color=layer4_color)
    draw_arrow(ax, (acn[0], acn[1] - 0.05), (cell[0], cell[1] + 0.05), color=layer4_color)
    draw_arrow(ax, (acn[0], acn[1] - 0.05), (whatsapp[0], whatsapp[1] + 0.05), color=layer4_color)

    # ── Offline-First Badge ────────────────────────────────
    offline_box = dict(boxstyle='round,pad=0.3', facecolor='#1a0a0a',
                       edgecolor='#ef4444', linewidth=1.5, alpha=0.9)
    ax.text(0.89, 0.90, '⚡ OFFLINE-FIRST', color='#ef4444', fontsize=7,
            ha='center', va='center', fontweight='bold', fontfamily='monospace',
            bbox=offline_box, zorder=5)

    # ── Data flow legend ──────────────────────────────────
    legend_y = 0.04
    legend_items = [
        (0.15, 'Data Sources', LAYER_BORDER['ingestion']),
        (0.35, 'AI Models', LAYER_BORDER['processing']),
        (0.55, 'Decision Engine', LAYER_BORDER['response']),
        (0.75, 'Alert Delivery', LAYER_BORDER['delivery']),
    ]
    for lx, label, color in legend_items:
        ax.plot(lx - 0.02, legend_y, 's', color=color, markersize=8, zorder=3)
        ax.text(lx + 0.01, legend_y, label, color=color, fontsize=7,
                ha='left', va='center', fontfamily='monospace', zorder=3)

    # ── Save ──────────────────────────────────────────────
    os.makedirs('pitch/assets', exist_ok=True)
    plt.savefig('pitch/assets/architecture_diagram.svg', format='svg',
                facecolor=BG, dpi=150, bbox_inches='tight')
    plt.savefig('pitch/assets/architecture_diagram.png', format='png',
                facecolor=BG, dpi=200, bbox_inches='tight')
    plt.close()
    print("✅ Architecture diagram saved to pitch/assets/architecture_diagram.svg and .png")


if __name__ == "__main__":
    generate_architecture_diagram()
