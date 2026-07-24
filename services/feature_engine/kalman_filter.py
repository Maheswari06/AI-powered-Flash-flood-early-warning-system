"""Extended Kalman Filter for sensor quality assurance.

Maintains one EKF instance per sensor stream (keyed by station_id).
State vector: [water_level, rate_of_change]
Observation model: direct water level reading.

Flags a reading as ANOMALY when innovation exceeds 3-sigma and
substitutes the predicted value with quality_flag = KALMAN_IMPUTED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

import numpy as np
import structlog

from services.feature_engine.schemas import KalmanOutput, QualityFlag

logger = structlog.get_logger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────
_PROCESS_NOISE_Q = 0.01   # Water levels change slowly
_OBSERVATION_NOISE_R = 0.5  # Sensor measurement error variance
_ANOMALY_SIGMA_THRESHOLD = 3.0  # Innovation threshold for anomaly detection
_DEFAULT_DT_HOURS = 5.0 / 60.0  # Default time step (5 minutes in hours)


class _KalmanState:
    """Internal per-sensor Kalman state."""

    __slots__ = ("x", "P", "last_ts")

    def __init__(self, initial_level: float, ts: datetime) -> None:
        # State: [water_level, rate_of_change (m/hr)]
        self.x: np.ndarray = np.array([initial_level, 0.0])
        # Covariance — moderate initial uncertainty
        self.P: np.ndarray = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
        ])
        self.last_ts: datetime = ts


class KalmanFilterBank:
    """Bank of per-station Extended Kalman Filters.

    Usage::

        kf_bank = KalmanFilterBank()
        result = kf_bank.update("CWC-HP-MANDI", timestamp, raw_level)
    """

    def __init__(
        self,
        q: float = _PROCESS_NOISE_Q,
        r: float = _OBSERVATION_NOISE_R,
        anomaly_threshold: float = _ANOMALY_SIGMA_THRESHOLD,
    ) -> None:
        self._q = q
        self._r = r
        self._threshold = anomaly_threshold
        self._states: Dict[str, _KalmanState] = {}

    # ── public API ─────────────────────────────────────────────────────

    def update(
        self,
        station_id: str,
        timestamp: datetime,
        raw_level: float,
    ) -> KalmanOutput:
        """Process one observation and return filtered output.

        Args:
            station_id: Gauge identifier.
            timestamp:  Observation UTC timestamp.
            raw_level:  Measured water level (m).

        Returns:
            KalmanOutput with filtered value and quality flag.
        """
        # Initialise state on first reading
        if station_id not in self._states:
            self._states[station_id] = _KalmanState(raw_level, timestamp)
            return KalmanOutput(
                station_id=station_id,
                timestamp=timestamp,
                raw_value=raw_level,
                filtered_value=raw_level,
                rate_of_change=0.0,
                quality_flag=QualityFlag.GOOD,
                innovation=0.0,
                innovation_sigma=np.sqrt(self._r),
                innovation_score=0.0,
            )

        state = self._states[station_id]

        # ── Time step ────────────────────────────────────
        dt = (timestamp - state.last_ts).total_seconds() / 3600.0  # hours
        if dt <= 0:
            dt = _DEFAULT_DT_HOURS

        # ── Predict ──────────────────────────────────────
        # State transition: level += rate_of_change * dt
        F = np.array([
            [1.0, dt],
            [0.0, 1.0],
        ])
        x_pred = F @ state.x

        # Process noise — scaled by dt
        Q = np.array([
            [self._q * dt**2, self._q * dt],
            [self._q * dt,    self._q],
        ])
        P_pred = F @ state.P @ F.T + Q

        # ── Innovation ───────────────────────────────────
        # Observation matrix: we observe water level directly
        H = np.array([[1.0, 0.0]])
        z = raw_level

        innovation = z - float(H @ x_pred)
        S = float(H @ P_pred @ H.T) + self._r  # Innovation covariance
        innovation_sigma = np.sqrt(S)
        innovation_score = abs(innovation) / innovation_sigma

        # ── Anomaly check ────────────────────────────────
        is_anomaly = innovation_score > self._threshold

        if is_anomaly:
            # Reject observation — use predicted value
            x_upd = x_pred.copy()
            P_upd = P_pred.copy()
            quality_flag = QualityFlag.KALMAN_IMPUTED
            filtered_value = float(x_pred[0])
            logger.warning(
                "kalman_anomaly_detected",
                station=station_id,
                raw=raw_level,
                predicted=float(x_pred[0]),
                innovation_score=round(innovation_score, 2),
            )
        else:
            # Standard Kalman update
            K = (P_pred @ H.T) / S  # Kalman gain (2×1)
            x_upd = x_pred + K.flatten() * innovation
            P_upd = (np.eye(2) - K @ H) @ P_pred
            quality_flag = QualityFlag.GOOD
            filtered_value = float(x_upd[0])

        # ── Store updated state ──────────────────────────
        state.x = x_upd
        state.P = P_upd
        state.last_ts = timestamp

        return KalmanOutput(
            station_id=station_id,
            timestamp=timestamp,
            raw_value=raw_level,
            filtered_value=round(filtered_value, 4),
            rate_of_change=round(float(x_upd[1]), 4),
            quality_flag=quality_flag,
            innovation=round(innovation, 4),
            innovation_sigma=round(innovation_sigma, 4),
            innovation_score=round(innovation_score, 4),
        )

    def reset(self, station_id: str) -> None:
        """Reset the Kalman state for a station (e.g. after maintenance)."""
        self._states.pop(station_id, None)
        logger.info("kalman_state_reset", station=station_id)

    def get_state_summary(self) -> Dict[str, Dict]:
        """Return a summary of all active KF states (for monitoring)."""
        return {
            sid: {
                "water_level": round(float(s.x[0]), 3),
                "rate_of_change": round(float(s.x[1]), 4),
                "last_ts": s.last_ts.isoformat(),
            }
            for sid, s in self._states.items()
        }
