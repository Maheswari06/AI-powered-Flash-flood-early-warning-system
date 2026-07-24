#!/usr/bin/env python3
"""Generate competitive comparison matrix SVG/PNG for pitch deck.

Produces a clean dark-themed table comparing ARGUS against
FFGS, Google FloodHub, IBM EWS, and typical hackathon projects.

Usage:
    python pitch/assets/generate_competitive_matrix.py
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# ── Color palette (ARGUS visual language) ────────────────────
BG       = "#050d1a"
CYAN     = "#00c9ff"
EMERALD  = "#10b981"
RED      = "#ef4444"
GREY     = "#6B7280"
DK_GREY  = "#1F2937"
WHITE    = "#f1f5f9"
AMBER    = "#f59e0b"


def generate_competitive_matrix():
    """Render the 7×5 competitive matrix as a publication-quality chart."""

    # ── Data ─────────────────────────────────────────────────
    capabilities = [
        "CV Virtual Gauging",
        "Causal Intervention",
        "Offline Edge AI",
        "Community NLP",
        "Parametric Insurance",
        "Prediction Lead Time",
        "New Hardware Cost",
    ]

    systems = ["FFGS", "Google\nFloodHub", "IBM\nEWS", "Typical\nHackathon", "ARGUS"]

    # Matrix: each row = capability, each col = system
    # Values: (display_text, is_positive)
    matrix = [
        # CV Virtual Gauging
        [("—", False), ("—", False), ("—", False), ("—", False), ("YOLO+SAM2", True)],
        # Causal Intervention
        [("—", False), ("—", False), ("—", False), ("—", False), ("GNN do-calc", True)],
        # Offline Edge AI
        [("—", False), ("—", False), ("Partial", None), ("—", False), ("ACN Mesh", True)],
        # Community NLP
        [("—", False), ("—", False), ("—", False), ("Basic", None), ("12 langs", True)],
        # Parametric Insurance
        [("—", False), ("—", False), ("—", False), ("—", False), ("FloodLedger", True)],
        # Lead Time
        [("1–6 hr", None), ("7 days\n(coarse)", None), ("12–24 hr", None), ("N/A", False), ("78 min\n(precise)", True)],
        # Hardware Cost
        [("₹3L/sensor", False), ("None", None), ("₹50L+ infra", False), ("None", None), ("₹0", True)],
    ]

    n_rows = len(capabilities)
    n_cols = len(systems)

    # ── Figure ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(18, 9))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(-0.5, n_rows + 0.5)
    ax.invert_yaxis()
    ax.axis("off")

    # ── Title ────────────────────────────────────────────────
    ax.text(
        (n_cols - 1) / 2, -0.9,
        "Competitive Landscape",
        fontsize=26, fontweight="bold", color=CYAN,
        ha="center", va="bottom", fontfamily="sans-serif",
    )
    ax.text(
        (n_cols - 1) / 2, -0.55,
        "ARGUS is not an incremental improvement. It is a new category.",
        fontsize=13, color=GREY, ha="center", va="bottom",
        fontstyle="italic", fontfamily="sans-serif",
    )

    cell_h = 0.85
    cell_pad = 0.08

    # ── Column headers ───────────────────────────────────────
    for j, sys_name in enumerate(systems):
        color = CYAN if j == n_cols - 1 else GREY
        weight = "bold" if j == n_cols - 1 else "normal"
        size = 14 if j == n_cols - 1 else 12

        # Highlight ARGUS column header
        if j == n_cols - 1:
            rect = mpatches.FancyBboxPatch(
                (j - 0.45, -0.45), 0.9, 0.8,
                boxstyle="round,pad=0.05",
                facecolor=CYAN + "15", edgecolor=CYAN + "40",
                linewidth=1.5,
            )
            ax.add_patch(rect)

        ax.text(
            j, 0, sys_name,
            fontsize=size, fontweight=weight, color=color,
            ha="center", va="center", fontfamily="sans-serif",
        )

    # ── Row headers (capabilities) ───────────────────────────
    for i, cap in enumerate(capabilities):
        row_y = i + 1
        ax.text(
            -0.48, row_y, cap,
            fontsize=12, color=WHITE, ha="right", va="center",
            fontfamily="sans-serif", fontweight="500",
        )
        # Subtle row divider
        ax.axhline(
            y=row_y - 0.48, xmin=0.0, xmax=1.0,
            color=DK_GREY, linewidth=0.5, alpha=0.6,
        )

    # ── Cells ────────────────────────────────────────────────
    for i in range(n_rows):
        row_y = i + 1
        for j in range(n_cols):
            text, is_positive = matrix[i][j]
            is_argus = j == n_cols - 1

            # Cell background for ARGUS column
            if is_argus:
                rect = mpatches.FancyBboxPatch(
                    (j - 0.44, row_y - 0.42), 0.88, cell_h,
                    boxstyle="round,pad=0.04",
                    facecolor=CYAN + "08", edgecolor=CYAN + "20",
                    linewidth=0.8,
                )
                ax.add_patch(rect)

            # Determine display
            if is_positive is True:
                icon = "[+] "
                color = CYAN if is_argus else EMERALD
                weight = "bold" if is_argus else "normal"
            elif is_positive is False:
                icon = "[x] " if text == "—" else ""
                color = "#4B5563"
                weight = "normal"
            else:  # None = neutral/partial
                icon = ""
                color = AMBER
                weight = "normal"

            display = f"{icon}{text}" if text != "—" else "—"
            size = 12 if is_argus else 11

            ax.text(
                j, row_y, display,
                fontsize=size, fontweight=weight, color=color,
                ha="center", va="center", fontfamily="sans-serif",
            )

    # ── Bottom divider ───────────────────────────────────────
    ax.axhline(
        y=n_rows + 0.52, xmin=0.0, xmax=1.0,
        color=DK_GREY, linewidth=0.5, alpha=0.6,
    )

    # ── Adjust layout ────────────────────────────────────────
    ax.set_xlim(-2.8, n_cols - 0.2)
    ax.set_ylim(n_rows + 0.8, -1.2)

    plt.tight_layout(pad=1.0)

    # ── Save ─────────────────────────────────────────────────
    svg_path = "pitch/assets/competitive_matrix.svg"
    png_path = "pitch/assets/competitive_matrix.png"

    plt.savefig(svg_path, format="svg", facecolor=BG, dpi=150, bbox_inches="tight")
    plt.savefig(png_path, format="png", facecolor=BG, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"✅ Competitive matrix saved to {svg_path} and .png")


if __name__ == "__main__":
    generate_competitive_matrix()
