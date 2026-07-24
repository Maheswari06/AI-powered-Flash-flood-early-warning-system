"""PINN terrain parameter updater.

When ScarNet detects significant terrain change, this module notifies
the Feature Engine (port 8003) to update PINN boundary conditions.

Specifically updates:
- Manning's roughness coefficient (changes with vegetation loss)
- Infiltration rate (changes with imperviousness increase)
- Catchment area connectivity (changes with slope failure)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import structlog

from services.scarnet.detection.change_detector import ChangeDetectionResult

logger = structlog.get_logger(__name__)


@dataclass
class PINNTerrainParams:
    """Updated hydrological parameters for the PINN model."""

    mannings_n_delta: float = 0.0       # Decrease with deforestation (faster flow)
    infiltration_rate_delta: float = 0.0  # Decrease with urbanization
    effective_impervious_area_fraction_delta: float = 0.0
    catchment_connectivity_change: str = "none"  # none, partial_blockage, new_channel
    source: str = "scarnet"
    confidence: float = 0.85

    def to_dict(self) -> dict:
        return {
            "mannings_n_delta": round(self.mannings_n_delta, 6),
            "infiltration_rate_delta": round(self.infiltration_rate_delta, 6),
            "effective_impervious_area_fraction_delta": round(
                self.effective_impervious_area_fraction_delta, 6
            ),
            "catchment_connectivity_change": self.catchment_connectivity_change,
            "source": self.source,
            "confidence": self.confidence,
        }


class PINNTerrainUpdater:
    """Triggers PINN model updates when significant terrain change detected.

    Communicates with the Feature Engine (port 8003) to update boundary
    conditions. If the Feature Engine is unavailable, logs the update
    parameters for manual application.
    """

    FEATURE_ENGINE_URL = "http://localhost:8003"

    def __init__(self, feature_engine_url: Optional[str] = None):
        if feature_engine_url:
            self.FEATURE_ENGINE_URL = feature_engine_url

    async def trigger_pinn_update(
        self, change_result: ChangeDetectionResult
    ) -> dict:
        """Send updated terrain parameters to Feature Engine.

        Returns the response or a status dict if the engine is unreachable.
        """
        if not change_result.pinn_update_required:
            logger.info("pinn_update_skipped", reason="No high/critical changes")
            return {"status": "skipped", "reason": "no_critical_changes"}

        params = self._compute_updated_params(change_result)

        logger.info(
            "pinn_terrain_update_triggered",
            mannings_delta=params.mannings_n_delta,
            infiltration_delta=params.infiltration_rate_delta,
            impervious_delta=params.effective_impervious_area_fraction_delta,
        )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.FEATURE_ENGINE_URL}/api/v1/pinn/update-terrain",
                    json=params.to_dict(),
                )
                if response.status_code == 200:
                    logger.info("pinn_update_success", response=response.json())
                    return {"status": "applied", "params": params.to_dict(), "response": response.json()}
                else:
                    logger.warning(
                        "pinn_update_http_error",
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    return {"status": "queued", "params": params.to_dict(), "http_code": response.status_code}

        except Exception as e:
            logger.warning("pinn_update_failed", error=str(e),
                           msg="Feature Engine unreachable — parameters logged for manual update")
            return {"status": "queued", "params": params.to_dict(), "error": str(e)}

    def _compute_updated_params(
        self, result: ChangeDetectionResult
    ) -> PINNTerrainParams:
        """Compute updated PINN boundary conditions from detected changes."""
        defor = next((c for c in result.changes if c.change_type == "DEFORESTATION"), None)
        urban = next((c for c in result.changes if c.change_type == "URBANIZATION"), None)
        slope = next((c for c in result.changes if c.change_type == "SLOPE_FAILURE"), None)

        # Manning's n decreases with deforestation → water flows faster
        # Forest: n ≈ 0.15, Bare soil: n ≈ 0.03
        # Change per 100 ha deforested: -0.003
        mannings_delta = -0.003 * (defor.area_hectares / 100) if defor else 0.0

        # Infiltration rate decreases with urbanization
        # Natural soil: ~50 mm/hr, Impervious: ~2 mm/hr
        # Change per 100 ha urbanized: -15% relative
        infiltration_delta = -0.15 * (urban.area_hectares / 100) if urban else 0.0

        # Impervious fraction increases with urbanization
        impervious_delta = urban.area_hectares / 10000 if urban else 0.0

        # Catchment connectivity
        connectivity = "none"
        if slope:
            connectivity = "partial_blockage" if slope.area_hectares < 10 else "major_blockage"

        confidence = min(
            c.confidence for c in result.changes
        ) if result.changes else 0.5

        return PINNTerrainParams(
            mannings_n_delta=mannings_delta,
            infiltration_rate_delta=infiltration_delta,
            effective_impervious_area_fraction_delta=impervious_delta,
            catchment_connectivity_change=connectivity,
            confidence=confidence,
        )
