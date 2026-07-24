"""ARGUS Phase 3 — Drift Detector.

Uses Evidently AI (when available) or scipy-based fallback
to compute Population Stability Index (PSI) and Kolmogorov-Smirnov
statistics for each feature column.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

log = structlog.get_logger(__name__)

try:
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset

    EVIDENTLY_AVAILABLE = True
except ImportError:
    EVIDENTLY_AVAILABLE = False


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two distributions."""
    eps = 1e-6
    e_hist, edges = np.histogram(expected, bins=bins, density=True)
    a_hist, _ = np.histogram(actual, bins=edges, density=True)
    e_hist = np.clip(e_hist, eps, None)
    a_hist = np.clip(a_hist, eps, None)
    return float(np.sum((a_hist - e_hist) * np.log(a_hist / e_hist)))


def ks_statistic(expected: np.ndarray, actual: np.ndarray) -> float:
    """Two-sample Kolmogorov-Smirnov statistic."""
    try:
        from scipy.stats import ks_2samp
        stat, _ = ks_2samp(expected, actual)
        return float(stat)
    except ImportError:
        # Manual ECDF comparison
        all_vals = np.concatenate([expected, actual])
        all_vals.sort()
        cdf_e = np.searchsorted(np.sort(expected), all_vals, side="right") / len(expected)
        cdf_a = np.searchsorted(np.sort(actual), all_vals, side="right") / len(actual)
        return float(np.max(np.abs(cdf_e - cdf_a)))


class DriftDetector:
    """Detect data drift across feature columns."""

    PSI_THRESHOLD = 0.2    # PSI > 0.2 → significant drift
    KS_THRESHOLD = 0.15    # KS > 0.15 → drift detected

    def detect(
        self,
        reference_data: Optional[Dict[str, np.ndarray]] = None,
        current_data: Optional[Dict[str, np.ndarray]] = None,
    ) -> Any:
        """Run drift detection, return a DriftReport-compatible dict."""
        # Lazy import to avoid circular
        from services.model_monitor.main import DriftReport, FeatureDrift

        if reference_data is None or current_data is None:
            log.info("drift_detect_no_data_provided")
            return DriftReport(
                report_id=f"drift_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                checked_at=datetime.utcnow().isoformat(),
            )

        features: List[FeatureDrift] = []
        drifted_count = 0

        for feat_name in reference_data:
            if feat_name not in current_data:
                continue
            ref = np.array(reference_data[feat_name])
            cur = np.array(current_data[feat_name])

            feat_psi = psi(ref, cur)
            feat_ks = ks_statistic(ref, cur)
            is_drifted = feat_psi > self.PSI_THRESHOLD or feat_ks > self.KS_THRESHOLD

            if is_drifted:
                drifted_count += 1

            features.append(FeatureDrift(
                feature=feat_name,
                psi=round(feat_psi, 4),
                ks_statistic=round(feat_ks, 4),
                drift_detected=is_drifted,
            ))

        total = len(features) or 1
        drift_share = drifted_count / total
        overall = drift_share > 0.3  # >30% features drifted

        report = DriftReport(
            report_id=f"drift_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            overall_drift=overall,
            dataset_drift_share=round(drift_share, 3),
            features=features,
            retrain_triggered=overall,
            checked_at=datetime.utcnow().isoformat(),
        )

        log.info(
            "drift_detected",
            overall=overall,
            drifted=drifted_count,
            total=total,
            share=drift_share,
        )

        return report
