"""4-second alert escalation engine for the Autonomous Crisis Node.

Escalation timeline (must complete within 4 seconds):

    T+0s  — Log alert to local SQLite + print coloured console line
    T+1s  — Trigger LoRa siren (lora_sim → play alert sound)
    T+2s  — Call Twilio IVR (if phone network available) OR log offline fallback
    T+4s  — Print "CELL BROADCAST TRIGGERED" (simulation)

Usage::

    from services.acn_node.alert_escalator import AlertEscalator
    esc = AlertEscalator(node_id="majuli", config=node_config, ...)
    esc.escalate(risk_score=0.85, features={...})
"""

from __future__ import annotations

import sys
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

from services.acn_node.offline_cache import OfflineCache
from services.acn_node.lora_sim import LoRaSirenSim

logger = structlog.get_logger(__name__)

# ANSI colours
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

# Alert level ordering (matches prediction service)
_LEVEL_PRIORITY = {
    "NORMAL": 0,
    "ADVISORY": 1,
    "WATCH": 2,
    "WARNING": 3,
    "EMERGENCY": 4,
}


def _classify_alert(
    risk_score: float,
    advisory_thresh: float,
    warning_thresh: float,
    emergency_thresh: float,
) -> str:
    """Map a risk score to an alert level using node-specific thresholds."""
    if risk_score >= emergency_thresh:
        return "EMERGENCY"
    if risk_score >= warning_thresh:
        return "WARNING"
    if risk_score >= advisory_thresh:
        return "ADVISORY"
    return "NORMAL"


class AlertEscalator:
    """4-second escalation pipeline for village-level flood alerts.

    Parameters
    ----------
    node_id : str
        Node identifier.
    config : dict
        Full node config (loaded from JSON).
    cache : OfflineCache
        SQLite cache for persisting alerts.
    siren : LoRaSirenSim
        LoRa siren simulator.
    """

    def __init__(
        self,
        node_id: str,
        config: Dict[str, Any],
        cache: OfflineCache,
        siren: LoRaSirenSim,
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._cache = cache
        self._siren = siren

        # Thresholds from config
        self._advisory = config.get("advisory_threshold", 0.35)
        self._warning = config.get("warning_threshold", 0.60)
        self._emergency = config.get("emergency_threshold", 0.82)

        # Escalation settings
        esc_cfg = config.get("escalation", {})
        self._lora_enabled = esc_cfg.get("lora_siren_enabled", True)
        self._twilio_enabled = esc_cfg.get("twilio_enabled", False)
        self._cell_broadcast_sim = esc_cfg.get("cell_broadcast_sim", True)
        self._alert_phones = esc_cfg.get("alert_phones", [])
        self._cooldown_sec = esc_cfg.get("cooldown_sec", 300)

        # Last alert timestamp (for cooldown)
        self._last_alert_ts: float = 0.0

    # ── Public API ───────────────────────────────────────────────────────

    def escalate(
        self,
        risk_score: float,
        features: Dict[str, float],
    ) -> str:
        """Run the full 4-second escalation pipeline.

        Returns the alert level string.
        """
        alert_level = _classify_alert(
            risk_score, self._advisory, self._warning, self._emergency
        )

        if alert_level == "NORMAL":
            # Still cache, but don't escalate
            self._cache.store_reading(features, risk_score, alert_level)
            return alert_level

        # Cooldown check — avoid siren fatigue
        now = time.monotonic()
        if (now - self._last_alert_ts) < self._cooldown_sec:
            logger.debug(
                "escalation_skipped_cooldown",
                node=self._node_id,
                remaining_sec=round(self._cooldown_sec - (now - self._last_alert_ts)),
            )
            self._cache.store_reading(features, risk_score, alert_level)
            return alert_level

        self._last_alert_ts = now

        # ── T+0s: Log to SQLite + console ────────────────────────────
        t_start = time.monotonic()
        self._step_log_alert(risk_score, alert_level, features)

        # ── T+1s: LoRa siren ─────────────────────────────────────────
        self._wait_until(t_start, 1.0)
        self._step_lora_siren(risk_score, alert_level)

        # ── T+2s: Twilio IVR ─────────────────────────────────────────
        self._wait_until(t_start, 2.0)
        self._step_twilio_ivr(risk_score, alert_level)

        # ── T+4s: Cell broadcast ──────────────────────────────────────
        self._wait_until(t_start, 4.0)
        self._step_cell_broadcast(risk_score, alert_level)

        elapsed = time.monotonic() - t_start
        logger.info(
            "escalation_complete",
            node=self._node_id,
            alert_level=alert_level,
            risk_score=round(risk_score, 4),
            elapsed_sec=round(elapsed, 2),
        )

        return alert_level

    # ── Escalation steps ─────────────────────────────────────────────────

    def _step_log_alert(
        self,
        risk_score: float,
        alert_level: str,
        features: Dict[str, float],
    ) -> None:
        """T+0s — Log to SQLite + print coloured console line."""
        self._cache.store_reading(features, risk_score, alert_level)

        colour = _RED if alert_level in ("WARNING", "EMERGENCY") else _YELLOW
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

        line = (
            f"{colour}{_BOLD}[{ts}] ⚠ ALERT: {alert_level} "
            f"| Node: {self._node_id} "
            f"| Risk: {risk_score:.4f} "
            f"| Level: {features.get('level_m', '?')}m "
            f"| Rain: {features.get('rainfall_mm', '?')}mm"
            f"{_RESET}"
        )
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

        logger.info(
            "alert_logged",
            node=self._node_id,
            step="T+0s",
            alert_level=alert_level,
            risk_score=round(risk_score, 4),
        )

    def _step_lora_siren(self, risk_score: float, alert_level: str) -> None:
        """T+1s — Trigger LoRa siren."""
        if not self._lora_enabled:
            self._print_step("T+1s", "LoRa siren DISABLED in config", _YELLOW)
            return

        self._print_step("T+1s", "LoRa siren TRIGGERED", _RED)
        self._siren.trigger(risk_score=risk_score, alert_level=alert_level)

    def _step_twilio_ivr(self, risk_score: float, alert_level: str) -> None:
        """T+2s — Call Twilio IVR or log offline fallback."""
        if not self._twilio_enabled:
            self._print_step(
                "T+2s",
                "Twilio IVR OFFLINE — phone network unavailable (logged for retry)",
                _YELLOW,
            )
            logger.info(
                "twilio_offline_fallback",
                node=self._node_id,
                step="T+2s",
                phones=self._alert_phones,
            )
            return

        # Real Twilio integration (optional dependency)
        try:
            self._call_twilio(risk_score, alert_level)
            self._print_step("T+2s", f"Twilio IVR called ({len(self._alert_phones)} numbers)", _GREEN)
        except Exception as exc:
            self._print_step("T+2s", f"Twilio FAILED: {exc} — logged offline", _RED)
            logger.error("twilio_call_error", node=self._node_id, error=str(exc))

    def _step_cell_broadcast(self, risk_score: float, alert_level: str) -> None:
        """T+4s — Simulate cell broadcast trigger."""
        if not self._cell_broadcast_sim:
            return

        colour = _RED if alert_level == "EMERGENCY" else _YELLOW
        banner = (
            f"\n{colour}{_BOLD}"
            f"┌──────────────────────────────────────────────────────┐\n"
            f"│  📡  CELL BROADCAST TRIGGERED                       │\n"
            f"│  Region: {self._config.get('region', 'Unknown'):<42}│\n"
            f"│  Alert:  {alert_level:<12}  Risk: {risk_score:.4f}            │\n"
            f"│  Message: Flash flood warning — move to high ground  │\n"
            f"└──────────────────────────────────────────────────────┘"
            f"{_RESET}\n"
        )
        sys.stdout.write(banner)
        sys.stdout.flush()

        logger.info(
            "cell_broadcast_triggered",
            node=self._node_id,
            step="T+4s",
            alert_level=alert_level,
            region=self._config.get("region"),
        )

    # ── Twilio helper ────────────────────────────────────────────────────

    def _call_twilio(self, risk_score: float, alert_level: str) -> None:
        """Make Twilio IVR calls (requires ``twilio`` package + env vars)."""
        import os

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_FROM_NUMBER")

        if not all([account_sid, auth_token, from_number]):
            raise RuntimeError("Twilio credentials not configured")

        from twilio.rest import Client  # type: ignore[import-untyped]

        client = Client(account_sid, auth_token)
        twiml = (
            f'<Response><Say voice="alice">'
            f"Flash flood {alert_level} alert for {self._config.get('region', 'your area')}. "
            f"Risk score {risk_score:.0%}. Move to high ground immediately."
            f"</Say></Response>"
        )
        for phone in self._alert_phones:
            client.calls.create(
                to=phone,
                from_=from_number,
                twiml=twiml,
            )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _wait_until(start: float, target_sec: float) -> None:
        """Sleep until *target_sec* seconds after *start*."""
        elapsed = time.monotonic() - start
        remaining = target_sec - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _print_step(step: str, message: str, colour: str = _CYAN) -> None:
        sys.stdout.write(f"{colour}  [{step}] {message}{_RESET}\n")
        sys.stdout.flush()
