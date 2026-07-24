"""IntersectionDetector — detects insured assets inside flood polygons.

Loads the insured-asset registry (CSV) and checks which assets fall
within a flood polygon (GeoJSON).  In demo mode a simple bounding-box
check is used instead of full Shapely geometry.
"""

from __future__ import annotations

import csv
import math
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from shared.models.phase2 import IntersectedAsset, PayoutRecord

logger = structlog.get_logger(__name__)


class IntersectionDetector:
    """Detect insured assets that fall within a flood polygon.

    Parameters
    ----------
    asset_registry_path:
        Path to a CSV with columns:
        ``asset_id, name, lat, lon, insured_value_inr, insurer_id``
    """

    def __init__(self, asset_registry_path: str = "./data/insured_assets.csv"):
        self.asset_registry_path = asset_registry_path
        self.assets: List[Dict[str, Any]] = []
        self._load_assets()

    def _load_assets(self) -> None:
        p = Path(self.asset_registry_path)
        if not p.exists():
            logger.warning("asset_registry_missing", path=self.asset_registry_path)
            return
        with open(p, newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                self.assets.append(
                    {
                        "asset_id": row["asset_id"],
                        "name": row["name"],
                        "lat": float(row["lat"]),
                        "lon": float(row["lon"]),
                        "insured_value_inr": float(row["insured_value_inr"]),
                        "insurer_id": row["insurer_id"],
                    }
                )
        logger.info("assets_loaded", count=len(self.assets))

    # ── Core detection ───────────────────────────────────────────────────

    def detect(
        self,
        flood_polygon_geojson: Optional[Dict[str, Any]] = None,
    ) -> List[IntersectedAsset]:
        """Return insured assets that intersect the flood polygon.

        When *flood_polygon_geojson* is ``None`` (demo) **all** assets are
        considered intersected.  Otherwise a simple bounding-box test is
        applied (production would use Shapely / GEOS).
        """
        if flood_polygon_geojson is None:
            # Demo: return all assets as intersected
            return [self._to_model(a) for a in self.assets]

        bbox = self._bbox(flood_polygon_geojson)
        if bbox is None:
            return [self._to_model(a) for a in self.assets]

        min_lat, min_lon, max_lat, max_lon = bbox
        intersected: List[IntersectedAsset] = []
        for asset in self.assets:
            if min_lat <= asset["lat"] <= max_lat and min_lon <= asset["lon"] <= max_lon:
                intersected.append(self._to_model(asset))
        return intersected

    def compute_payouts(
        self,
        event_id: str,
        intersected: List[IntersectedAsset],
        severity: str = "SEVERE",
    ) -> List[PayoutRecord]:
        """Generate parametric payout records for intersected assets."""
        factor = {"WARNING": 0.25, "SEVERE": 0.50, "EXTREME": 0.75}.get(severity, 0.50)
        payouts: List[PayoutRecord] = []
        for asset in intersected:
            payouts.append(
                PayoutRecord(
                    event_id=event_id,
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    amount_inr=round(asset.insured_value_inr * factor, 2),
                    insurer_id=asset.insurer_id,
                )
            )
        return payouts

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_model(asset: Dict[str, Any]) -> IntersectedAsset:
        return IntersectedAsset(
            asset_id=asset["asset_id"],
            name=asset["name"],
            lat=asset["lat"],
            lon=asset["lon"],
            insured_value_inr=asset["insured_value_inr"],
            insurer_id=asset["insurer_id"],
        )

    @staticmethod
    def _bbox(
        geojson: Dict[str, Any],
    ) -> Optional[tuple]:
        """Extract bounding box (min_lat, min_lon, max_lat, max_lon)."""
        try:
            coords = geojson.get("coordinates", [[]])[0]
            if not coords:
                return None
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]
            return min(lats), min(lons), max(lats), max(lons)
        except Exception:
            return None
