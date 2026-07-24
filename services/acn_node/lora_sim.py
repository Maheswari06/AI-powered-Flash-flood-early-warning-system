"""LoRaWAN siren trigger simulator.

On a real ACN deployment this module would drive a LoRa-connected
village siren via SX1276/SX1262 radio.  In simulation / demo mode
it:

  1. Prints a bold ANSI-coloured alert banner to the console.
  2. Attempts to play a WAV/MP3 alert sound (via ``playsound``).
  3. Falls back to terminal bell (``\\a``) if ``playsound`` is unavailable.

Usage::

    from services.acn_node.lora_sim import LoRaSirenSim
    siren = LoRaSirenSim(node_id="majuli", duration_sec=10)
    siren.trigger(risk_score=0.87, alert_level="EMERGENCY")
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# ANSI colour codes
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_BLINK = "\033[5m"
_RESET = "\033[0m"

# Alert sound search paths (relative to project root)
_SOUND_SEARCH = [
    "./data/siren_alert.wav",
    "./data/siren_alert.mp3",
    "./data/alert.wav",
    "./data/alert.mp3",
]


class LoRaSirenSim:
    """Simulate a LoRaWAN village siren trigger.

    Parameters
    ----------
    node_id : str
        Node identifier for logging.
    duration_sec : int
        How long the siren runs (simulated via sleep in separate thread).
    sound_path : str | None
        Explicit path to alert sound file.  Auto-searches if *None*.
    """

    def __init__(
        self,
        node_id: str = "unknown",
        duration_sec: int = 10,
        sound_path: Optional[str] = None,
    ) -> None:
        self._node_id = node_id
        self._duration = duration_sec
        self._sound_path = self._resolve_sound(sound_path)
        self._active = False

    # ── Sound resolution ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_sound(explicit: Optional[str]) -> Optional[str]:
        if explicit and Path(explicit).exists():
            return explicit
        for candidate in _SOUND_SEARCH:
            if Path(candidate).exists():
                return candidate
        return None

    # ── Trigger ──────────────────────────────────────────────────────────

    def trigger(
        self,
        risk_score: float,
        alert_level: str = "WARNING",
    ) -> None:
        """Fire the siren simulation.

        * Prints coloured banner to stdout.
        * Plays alert sound (non-blocking thread).
        * Logs the event.
        """
        if self._active:
            logger.debug("siren_already_active", node=self._node_id)
            return

        self._active = True

        # Console banner
        self._print_banner(risk_score, alert_level)

        # Sound (non-blocking)
        t = threading.Thread(
            target=self._play_sound,
            daemon=True,
            name=f"siren-{self._node_id}",
        )
        t.start()

        logger.info(
            "lora_siren_triggered",
            node=self._node_id,
            risk_score=round(risk_score, 4),
            alert_level=alert_level,
            duration_sec=self._duration,
        )

        # Schedule deactivation
        threading.Timer(self._duration, self._deactivate).start()

    def _deactivate(self) -> None:
        self._active = False
        logger.debug("siren_deactivated", node=self._node_id)

    # ── Console banner ───────────────────────────────────────────────────

    def _print_banner(self, risk_score: float, alert_level: str) -> None:
        colour = _RED if alert_level in ("WARNING", "EMERGENCY") else _YELLOW
        banner = (
            f"\n{colour}{_BOLD}{_BLINK}"
            f"╔══════════════════════════════════════════════════════╗\n"
            f"║  🚨  LoRa SIREN ACTIVATED — {alert_level:<12}          ║\n"
            f"║  Node: {self._node_id:<15}  Risk: {risk_score:.2f}              ║\n"
            f"║  Action: EVACUATE TO HIGH GROUND IMMEDIATELY        ║\n"
            f"╚══════════════════════════════════════════════════════╝"
            f"{_RESET}\n"
        )
        sys.stdout.write(banner)
        sys.stdout.flush()

    # ── Sound playback ───────────────────────────────────────────────────

    def _play_sound(self) -> None:
        """Try playsound → terminal bell fallback."""
        if self._sound_path:
            try:
                from playsound import playsound  # type: ignore[import-untyped]

                playsound(self._sound_path)
                return
            except ImportError:
                logger.debug("playsound_not_installed_using_bell")
            except Exception as exc:
                logger.debug("playsound_error", error=str(exc))

        # Terminal bell fallback (3 beeps)
        for _ in range(3):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.5)
