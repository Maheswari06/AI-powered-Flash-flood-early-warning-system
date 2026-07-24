"""MirrorReportGenerator — NDMA-format PDF report for counterfactual analysis.

Uses ReportLab for PDF generation with charts and tables.
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab_not_installed", msg="PDF generation unavailable")


class MirrorReportGenerator:
    """Generates NDMA-format PDF reports for counterfactual analyses."""

    def __init__(self):
        if REPORTLAB_AVAILABLE:
            self._styles = getSampleStyleSheet()
            self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Add HYDRA-branded styles."""
        self._styles.add(ParagraphStyle(
            "HydraTitle",
            parent=self._styles["Title"],
            fontSize=22,
            textColor=colors.HexColor("#1a365d"),
            spaceAfter=6 * mm,
        ))
        self._styles.add(ParagraphStyle(
            "HydraHeading",
            parent=self._styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#2b6cb0"),
            spaceBefore=8 * mm,
            spaceAfter=4 * mm,
        ))
        self._styles.add(ParagraphStyle(
            "HydraBody",
            parent=self._styles["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
        ))
        self._styles.add(ParagraphStyle(
            "HydraCaption",
            parent=self._styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
        ))

    def generate_pdf(
        self,
        event_dict: Dict[str, Any],
        counterfactual_results: List[Dict[str, Any]],
    ) -> bytes:
        """Generate a full NDMA-format PDF report.

        Returns PDF as bytes.
        """
        if not REPORTLAB_AVAILABLE:
            return self._generate_text_fallback(event_dict, counterfactual_results)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
        )

        story = []

        # ── Title Page ───────────────────────────────────────────────
        story.append(Spacer(1, 30 * mm))
        story.append(Paragraph("HYDRA — MIRROR Engine", self._styles["HydraTitle"]))
        story.append(Paragraph(
            "Counterfactual Analysis Report",
            self._styles["Heading1"],
        ))
        story.append(Spacer(1, 10 * mm))
        story.append(HRFlowable(
            width="100%", thickness=2,
            color=colors.HexColor("#2b6cb0"),
        ))
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            f"<b>Event:</b> {event_dict.get('name', 'Unknown')}",
            self._styles["HydraBody"],
        ))
        story.append(Paragraph(
            f"<b>Date:</b> {event_dict.get('date', 'N/A')}",
            self._styles["HydraBody"],
        ))
        story.append(Paragraph(
            f"<b>Location:</b> {event_dict.get('location', 'N/A')}",
            self._styles["HydraBody"],
        ))
        story.append(Paragraph(
            f"<b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            self._styles["HydraBody"],
        ))
        story.append(Spacer(1, 15 * mm))

        # Key metrics box
        actual_deaths = event_dict.get("lives_lost", 0)
        peak_depth = event_dict.get("peak_flood_depth_m", 0)
        damage = event_dict.get("damage_crore_inr", 0)
        affected = event_dict.get("affected_population", 0)

        metrics_data = [
            ["Metric", "Actual Outcome"],
            ["Lives Lost", str(actual_deaths)],
            ["Peak Flood Depth", f"{peak_depth} m"],
            ["Damage (₹ Crore)", f"₹{damage:,}"],
            ["Affected Population", f"{affected:,}"],
            ["Warning Lead Time", f"{abs(event_dict.get('official_warning_time_min', 0))} min"],
        ]
        metrics_table = Table(metrics_data, colWidths=[55 * mm, 55 * mm])
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(metrics_table)
        story.append(PageBreak())

        # ── Event Timeline ───────────────────────────────────────────
        story.append(Paragraph("1. Event Timeline", self._styles["HydraHeading"]))
        timeline = event_dict.get("timeline", [])
        if timeline:
            tl_data = [["T (min)", "Water (m)", "Rain (mm/hr)", "Risk", "Event"]]
            for t in timeline:
                tl_data.append([
                    str(t.get("t_min", "")),
                    str(t.get("water_level_m", "")),
                    str(t.get("rainfall_mm_hr", "")),
                    f"{t.get('risk_score', 0):.2f}",
                    str(t.get("event", ""))[:40],
                ])
            tl_table = Table(tl_data, colWidths=[18 * mm, 20 * mm, 22 * mm, 15 * mm, 80 * mm])
            tl_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(tl_table)
        story.append(PageBreak())

        # ── Counterfactual Results ───────────────────────────────────
        story.append(Paragraph("2. Counterfactual Analysis", self._styles["HydraHeading"]))
        story.append(Paragraph(
            "The following scenarios explore alternate outcomes under different "
            "intervention strategies. Each counterfactual modifies one aspect of "
            "the actual event response to estimate the impact on casualties, "
            "flood depth, and economic damage.",
            self._styles["HydraBody"],
        ))
        story.append(Spacer(1, 5 * mm))

        for i, cf in enumerate(counterfactual_results):
            story.append(Paragraph(
                f"2.{i + 1}  {cf.get('cf_label', cf.get('cf_id', ''))}",
                self._styles["Heading3"],
            ))
            story.append(Paragraph(
                cf.get("description", ""),
                self._styles["HydraBody"],
            ))
            story.append(Spacer(1, 3 * mm))

            # Intervention actions
            actions = cf.get("intervention_actions", [])
            for action in actions:
                story.append(Paragraph(f"• {action}", self._styles["HydraBody"]))
            story.append(Spacer(1, 3 * mm))

            # Result metrics
            cf_data = [
                ["Metric", "Actual", "Counterfactual", "Δ"],
                [
                    "Lives Lost",
                    str(actual_deaths),
                    str(cf.get("casualties_estimate", "?")),
                    f"-{cf.get('lives_saved_estimate', 0)} saved",
                ],
                [
                    "Peak Depth (m)",
                    str(peak_depth),
                    str(cf.get("peak_depth_m", "?")),
                    f"{peak_depth - cf.get('peak_depth_m', peak_depth):+.2f}m",
                ],
                [
                    "Damage Avoided",
                    f"₹{damage:,} Cr",
                    f"-₹{cf.get('damage_avoided_crore', 0):,.0f} Cr",
                    f"{cf.get('area_reduction_pct', 0):.1f}% area",
                ],
            ]
            cf_table = Table(cf_data, colWidths=[35 * mm, 30 * mm, 38 * mm, 35 * mm])
            cf_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#38a169")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(cf_table)
            story.append(Paragraph(
                f"Confidence: {cf.get('confidence', 0):.0%} — {cf.get('methodology', '')}",
                self._styles["HydraCaption"],
            ))
            story.append(Spacer(1, 6 * mm))

        # ── Summary Ranking ──────────────────────────────────────────
        story.append(PageBreak())
        story.append(Paragraph("3. Intervention Ranking", self._styles["HydraHeading"]))
        story.append(Paragraph(
            "Counterfactual scenarios ranked by estimated lives saved:",
            self._styles["HydraBody"],
        ))
        story.append(Spacer(1, 4 * mm))

        sorted_cfs = sorted(
            counterfactual_results,
            key=lambda x: x.get("lives_saved_estimate", 0),
            reverse=True,
        )
        rank_data = [["Rank", "Scenario", "Lives Saved", "Damage Avoided", "Confidence"]]
        for rank, cf in enumerate(sorted_cfs, 1):
            rank_data.append([
                str(rank),
                cf.get("cf_label", cf.get("cf_id", "")),
                str(cf.get("lives_saved_estimate", 0)),
                f"₹{cf.get('damage_avoided_crore', 0):,.0f} Cr",
                f"{cf.get('confidence', 0):.0%}",
            ])
        rank_table = Table(rank_data, colWidths=[12 * mm, 45 * mm, 25 * mm, 35 * mm, 25 * mm])
        rank_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(rank_table)
        story.append(Spacer(1, 10 * mm))

        # ── Footer ───────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            "Report generated by HYDRA MIRROR Engine v2.1 — "
            "For research purposes only. Counterfactual estimates are model-based "
            "and should not replace expert judgment.",
            self._styles["HydraCaption"],
        ))
        story.append(Paragraph(
            "NDMA Reference: Flood Management Manual 2023 | "
            "CWC Flood Forecasting Standards",
            self._styles["HydraCaption"],
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        logger.info("pdf_generated", size_kb=len(pdf_bytes) // 1024)
        return pdf_bytes

    def generate_intervention_timeline(
        self, slider_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format slider data for frontend chart consumption."""
        return {
            "chart_type": "intervention_slider",
            "x_axis": "time_before_peak_min",
            "y_axes": [
                {"key": "lives_saved_estimate", "label": "Lives Saved", "color": "#38a169"},
                {"key": "peak_depth_m", "label": "Peak Depth (m)", "color": "#e53e3e"},
                {"key": "damage_reduction_pct", "label": "Damage Reduction %", "color": "#3182ce"},
            ],
            "data": slider_data,
        }

    def _generate_text_fallback(
        self,
        event_dict: Dict[str, Any],
        counterfactual_results: List[Dict[str, Any]],
    ) -> bytes:
        """Plain-text fallback when ReportLab is not installed."""
        lines = [
            "=" * 60,
            "HYDRA — MIRROR Engine Counterfactual Report",
            "=" * 60,
            f"Event: {event_dict.get('name', 'Unknown')}",
            f"Date:  {event_dict.get('date', 'N/A')}",
            f"Location: {event_dict.get('location', 'N/A')}",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "ACTUAL OUTCOMES:",
            f"  Lives lost: {event_dict.get('lives_lost', '?')}",
            f"  Peak depth: {event_dict.get('peak_flood_depth_m', '?')} m",
            f"  Damage: ₹{event_dict.get('damage_crore_inr', '?')} Crore",
            "",
            "-" * 60,
            "COUNTERFACTUAL SCENARIOS:",
            "",
        ]
        for cf in counterfactual_results:
            lines.extend([
                f"  [{cf.get('cf_id')}] {cf.get('cf_label')}",
                f"    {cf.get('description', '')}",
                f"    Lives saved: {cf.get('lives_saved_estimate', '?')}",
                f"    Peak depth: {cf.get('peak_depth_m', '?')} m",
                f"    Damage avoided: ₹{cf.get('damage_avoided_crore', '?')} Cr",
                f"    Confidence: {cf.get('confidence', 0):.0%}",
                "",
            ])
        lines.extend([
            "-" * 60,
            "HYDRA MIRROR Engine v2.1 — Research use only",
            "=" * 60,
        ])
        return "\n".join(lines).encode("utf-8")
