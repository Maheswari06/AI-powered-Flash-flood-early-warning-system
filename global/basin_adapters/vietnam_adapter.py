"""
ARGUS Phase 6 — Vietnam Mekong Delta Adapter

Adapts ARGUS for Vietnam Mekong Delta deployment.

Key differences from India/Bangladesh:
  - River: Mekong (flows from China → Myanmar → Laos → Thailand → Cambodia → Vietnam)
  - Data: VNMHA (Vietnam Meteorological Hydrological Administration)
  - 6-country transboundary coordination via Mekong River Commission (MRC)
  - Tidal influence: Mekong Delta floods are compound events (rain + tide)
  - Language: Vietnamese (vi) + Khmer for Mekong Delta ethnic minorities
  - Agriculture: 50% of Vietnam's rice — FloodLedger for crop insurance
  - Salinity intrusion: secondary hazard ARGUS can model as causal node
  - Longest upstream warning in ARGUS: Chiang Saen → Delta ~3 weeks
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MekongBasinConfig:
    """Vietnam Mekong-specific basin configuration."""
    basin_id: str = "mekong_vietnam"
    display_name: str = "Mekong Delta — Vietnam"
    country: str = "Vietnam"
    bbox: tuple = (104.5, 8.5, 107.0, 11.5)
    flash_flood_threshold_hours: int = 12  # slower, compound floods
    monsoon_months: list = None
    language_codes: list = None
    admin_unit_hierarchy: list = None
    upstream_countries: list = None
    upstream_lag_days_max: int = 21  # Chiang Saen → Delta takes ~3 weeks

    def __post_init__(self):
        if self.monsoon_months is None:
            self.monsoon_months = [7, 8, 9, 10, 11]  # Southwest monsoon
        if self.language_codes is None:
            self.language_codes = ["vi", "km", "en"]  # Vietnamese, Khmer, English
        if self.admin_unit_hierarchy is None:
            self.admin_unit_hierarchy = ["province", "district", "commune", "village"]
        if self.upstream_countries is None:
            self.upstream_countries = [
                "China", "Myanmar", "Laos", "Thailand", "Cambodia"
            ]


@dataclass
class TidalSurgeReading:
    """Tidal surge observation for compound flood modeling."""
    station_id: str
    level_m: float
    predicted_high_m: float
    predicted_low_m: float
    timestamp: str
    spring_tide: bool = False


@dataclass
class SalinityReading:
    """Salinity intrusion measurement — secondary hazard."""
    station_id: str
    salinity_ppt: float      # parts per thousand
    distance_from_coast_km: float
    timestamp: str
    risk_level: str = "NORMAL"   # NORMAL / ELEVATED / CRITICAL


class VietnamMekongAdapter:
    """
    Adapts ARGUS for Vietnam Mekong Delta deployment.

    Mekong Delta specific challenges:
      1. COMPOUND FLOODING: Upstream river flood + downstream tidal surge
         happen simultaneously during monsoon + spring tides.
      2. SALINITY INTRUSION: When river flow drops, seawater pushes inland,
         destroying 50% of Vietnam's rice paddies.
      3. EXTREMELY FLAT: The delta is 0–3m above sea level. Small water level
         changes inundate enormous areas.
      4. TRANSBOUNDARY: 6 countries share the Mekong. China's dams
         (the Lancang cascade) control upstream flow.

    ARGUS models all four as nodes in the causal DAG.
    """

    MRC_API = "https://www.mrcmekong.org/api/hydro"
    VNMHA_API = "https://kttvqg.gov.vn/api/hydro"
    TIDAL_API = "https://tides.mobilegeographics.com/api"

    # Key MRC stations along the Mekong
    MRC_STATIONS = {
        "chiang_saen": {"country": "Thailand", "km_from_delta": 2400, "lag_days": 21},
        "vientiane": {"country": "Laos", "km_from_delta": 1800, "lag_days": 14},
        "nakhon_phanom": {"country": "Thailand", "km_from_delta": 1400, "lag_days": 10},
        "stung_treng": {"country": "Cambodia", "km_from_delta": 600, "lag_days": 5},
        "phnom_penh": {"country": "Cambodia", "km_from_delta": 330, "lag_days": 3},
        "tan_chau": {"country": "Vietnam", "km_from_delta": 200, "lag_days": 2},
        "can_tho": {"country": "Vietnam", "km_from_delta": 80, "lag_days": 1},
    }

    def __init__(self):
        self.config = MekongBasinConfig()
        self.logger = logger.bind(adapter="vietnam_mekong")

    def get_basin_config(self) -> MekongBasinConfig:
        """Return Mekong Delta basin configuration."""
        return self.config

    # ── Compound Flood DAG Extensions ────────────────────────────────────

    def add_tidal_causal_node(self, dag_edges: List[dict]) -> List[dict]:
        """
        Extends the standard ARGUS DAG with tidal surge nodes.
        Compound flooding = river_flood AND tidal_surge simultaneously.

        Returns updated list of DAG edges for the causal engine.
        """
        tidal_nodes = [
            {
                "source": "tidal_surge_level",
                "target": "compound_flood_risk",
                "lag_minutes": 0,
                "causal_type": "AMPLIFIER",
                "weight": 0.7,
                "mechanism": "tidal",
                "description": "Spring tide amplifies river flood depth"
            },
            {
                "source": "river_level_delta",
                "target": "compound_flood_risk",
                "lag_minutes": 30,
                "causal_type": "PRIMARY",
                "weight": 0.9,
                "mechanism": "hydrological",
                "description": "Upstream river discharge is primary flood driver"
            },
            {
                "source": "wind_speed_coastal",
                "target": "tidal_surge_level",
                "lag_minutes": 60,
                "causal_type": "CONTRIBUTING",
                "weight": 0.5,
                "mechanism": "meteorological",
                "description": "Onshore wind elevates tidal surge"
            },
        ]

        salinity_nodes = [
            {
                "source": "river_discharge_low",
                "target": "salinity_intrusion_km",
                "lag_minutes": 720,  # 12 hours
                "causal_type": "PRIMARY",
                "weight": 0.85,
                "mechanism": "hydrological",
                "description": "Low river flow allows seawater intrusion"
            },
            {
                "source": "tidal_surge_level",
                "target": "salinity_intrusion_km",
                "lag_minutes": 120,
                "causal_type": "AMPLIFIER",
                "weight": 0.6,
                "mechanism": "tidal",
                "description": "High tide pushes salt front further inland"
            },
        ]

        extended = dag_edges + tidal_nodes + salinity_nodes
        self.logger.info(
            "dag_extended_for_compound_flood",
            tidal_edges=len(tidal_nodes),
            salinity_edges=len(salinity_nodes),
            total_edges=len(extended),
        )
        return extended

    # ── MRC Upstream Signal ──────────────────────────────────────────────

    async def get_mrc_upstream_signal(self) -> Dict[str, Any]:
        """
        Mekong River Commission provides 5-day upstream discharge forecasts.
        A flood at Chiang Saen (Thailand) reaches Vietnam's delta in ~3 weeks.
        This is ARGUS's longest upstream warning — critical for Vietnam.

        Returns upstream station data keyed by station name.
        """
        signals = {}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{self.MRC_API}/discharge/forecast",
                    params={"stations": ",".join(self.MRC_STATIONS.keys())}
                )
                r.raise_for_status()

                for station_data in r.json().get("stations", []):
                    station_id = station_data.get("id", "")
                    meta = self.MRC_STATIONS.get(station_id, {})
                    signals[station_id] = {
                        "discharge_cumecs": station_data.get("discharge", 0),
                        "trend": station_data.get("trend", "stable"),
                        "country": meta.get("country", "Unknown"),
                        "km_from_delta": meta.get("km_from_delta", 0),
                        "estimated_lag_days": meta.get("lag_days", 0),
                        "timestamp": station_data.get("timestamp", ""),
                    }
        except Exception as e:
            self.logger.warning(
                "mrc_upstream_unavailable",
                error=str(e),
                fallback="historical_average",
            )
            # Fallback: use historical averages for the current month
            signals = self._historical_mrc_averages()

        self.logger.info(
            "mrc_signals_fetched",
            stations=len(signals),
            furthest_signal_days=max(
                (s.get("estimated_lag_days", 0) for s in signals.values()),
                default=0,
            ),
        )
        return signals

    def _historical_mrc_averages(self) -> Dict[str, Any]:
        """Fallback historical averages when MRC API is unavailable."""
        month = datetime.utcnow().month
        # Approximate monthly averages at Chiang Saen (m³/s)
        monthly_avg = {
            1: 1200, 2: 900, 3: 800, 4: 900,
            5: 2500, 6: 4500, 7: 7500, 8: 12000,
            9: 14000, 10: 10000, 11: 5000, 12: 2500,
        }
        avg_discharge = monthly_avg.get(month, 5000)
        return {
            station: {
                "discharge_cumecs": avg_discharge * (1 - 0.1 * meta["lag_days"] / 21),
                "trend": "rising" if month in [5, 6, 7, 8] else "falling",
                "country": meta["country"],
                "km_from_delta": meta["km_from_delta"],
                "estimated_lag_days": meta["lag_days"],
                "timestamp": datetime.utcnow().isoformat(),
                "source": "historical_average",
            }
            for station, meta in self.MRC_STATIONS.items()
        }

    # ── Tidal Data ───────────────────────────────────────────────────────

    async def get_tidal_forecast(self) -> List[TidalSurgeReading]:
        """
        Get tidal surge forecast for Mekong Delta.
        Critical for compound flood modeling.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{self.VNMHA_API}/tidal_forecast",
                    params={"region": "mekong_delta"},
                )
                r.raise_for_status()
                return [
                    TidalSurgeReading(
                        station_id=s["id"],
                        level_m=s["current_level"],
                        predicted_high_m=s["predicted_high"],
                        predicted_low_m=s["predicted_low"],
                        timestamp=s["timestamp"],
                        spring_tide=s.get("spring_tide", False),
                    )
                    for s in r.json().get("stations", [])
                ]
        except Exception:
            self.logger.warning("tidal_forecast_unavailable")
            return []

    async def get_salinity_readings(self) -> List[SalinityReading]:
        """
        Get salinity intrusion readings from VNMHA.
        Salinity > 4 ppt destroys rice crops — a secondary hazard.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{self.VNMHA_API}/salinity/current",
                    params={"region": "mekong_delta"},
                )
                r.raise_for_status()
                readings = []
                for s in r.json().get("stations", []):
                    salinity = float(s.get("salinity_ppt", 0))
                    risk = (
                        "CRITICAL" if salinity > 4.0
                        else "ELEVATED" if salinity > 2.0
                        else "NORMAL"
                    )
                    readings.append(SalinityReading(
                        station_id=s["id"],
                        salinity_ppt=salinity,
                        distance_from_coast_km=float(s.get("distance_coast_km", 0)),
                        timestamp=s.get("timestamp", ""),
                        risk_level=risk,
                    ))
                return readings
        except Exception:
            self.logger.warning("salinity_readings_unavailable")
            return []

    # ── Alert Translation ────────────────────────────────────────────────

    def translate_alert_for_vietnam(self, alert: dict) -> dict:
        """
        Translate ARGUS alert to VNMHA standard alert format.
        Adds compound flood indicators for the Mekong Delta context.
        """
        return {
            "maDonVi": alert.get("alert_id", ""),
            "mucBaoDong": self._map_to_vnmha_level(alert.get("alert_level", "")),
            "tenSong": "Sông Mê Kông",
            "tram": alert.get("station_name", ""),
            "mucNuocDuBao": alert.get("predicted_level_m", 0),
            "mucBaoDongNguyCap": alert.get("danger_level_m", 0),
            "thoiGianDuBao": alert.get("predicted_flood_time", ""),
            "nguonPhatHanh": "Hệ thống ARGUS AI",
            "doTinCay": alert.get("confidence", 0),
            "nguonThuongNguon": "MRC — 21 ngày tín hiệu thượng nguồn",
            "ngonNgu": "vi",
            "thongBaoVietnamese": self._generate_vietnamese_alert(alert),
            "luLutKepPhuc": True,  # compound flood flag
        }

    def _map_to_vnmha_level(self, argus_level: str) -> int:
        """Map ARGUS alert level to VNMHA numeric level (1-5)."""
        mapping = {"WATCH": 2, "WARNING": 3, "CRITICAL": 5}
        return mapping.get(argus_level, 1)

    def _generate_vietnamese_alert(self, alert: dict) -> str:
        """Generate alert message in Vietnamese."""
        level_vi = {
            "WATCH": "Cảnh báo",
            "WARNING": "Cảnh báo lũ",
            "CRITICAL": "Nguy hiểm - Lũ nghiêm trọng",
        }
        level_text = level_vi.get(alert.get("alert_level", ""), "Thông báo")
        return (
            f"⚠️ {level_text} — Sông Mê Kông\n"
            f"Mực nước dự báo: {alert.get('predicted_level_m', 0):.1f}m\n"
            f"Mức báo động: {alert.get('danger_level_m', 0):.1f}m\n"
            f"Độ tin cậy: {int(alert.get('confidence', 0) * 100)}%\n"
            f"Di chuyển đến nơi an toàn ngay."
        )

    # ── Rice Crop Insurance (FloodLedger) ────────────────────────────────

    def compute_rice_crop_damage_estimate(
        self,
        inundation_depth_m: float,
        inundation_duration_hours: int,
        growth_stage: str = "vegetative",
    ) -> dict:
        """
        Estimate rice crop damage for FloodLedger parametric insurance.
        Mekong Delta produces 50% of Vietnam's rice — ~25M tonnes/year.

        Damage model based on IRRI (Int'l Rice Research Institute) data:
          - < 0.3m for < 3 days: minimal damage (~10%)
          - > 0.5m for > 5 days: total crop loss (100%)
          - Growth stage matters: flowering stage is most vulnerable
        """
        stage_vulnerability = {
            "seedling": 0.8,
            "vegetative": 0.6,
            "flowering": 1.0,   # Most vulnerable
            "grain_filling": 0.9,
            "mature": 0.4,
        }

        vulnerability = stage_vulnerability.get(growth_stage, 0.6)

        # Depth-duration damage function
        depth_factor = min(1.0, inundation_depth_m / 0.5)
        duration_factor = min(1.0, inundation_duration_hours / 120)  # 5 days

        damage_fraction = min(1.0, depth_factor * duration_factor * vulnerability)

        # Average value per hectare (USD)
        avg_value_per_ha_usd = 2500  # ~2 crops/year

        return {
            "damage_fraction": round(damage_fraction, 3),
            "damage_percent": round(damage_fraction * 100, 1),
            "estimated_loss_per_ha_usd": round(damage_fraction * avg_value_per_ha_usd),
            "growth_stage": growth_stage,
            "vulnerability_factor": vulnerability,
            "inundation_depth_m": inundation_depth_m,
            "inundation_duration_hours": inundation_duration_hours,
            "payout_eligible": damage_fraction > 0.3,  # 30% threshold
        }
