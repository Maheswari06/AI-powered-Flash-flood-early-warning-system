"""
ARGUS SDK — Basin Configuration

Describes a river basin for ARGUS deployment.
Create from YAML config, programmatically, or from the ARGUS Foundation registry.

Example basin.yaml:
    basin_id: kaveri_karnataka
    display_name: Kaveri River — Karnataka
    country: India
    state: Karnataka
    bbox: [75.0, 11.5, 79.5, 13.5]
    languages: [kn, ta, hi]
    data_sources:
      rainfall: open_meteo        # Free, no key
      gauges:   cwc_wris          # Free registration
      satellite: copernicus       # Free registration
    monsoon_months: [6, 7, 8, 9, 10]
    flash_flood_hours: 3
    contact_authority: ksndmc@karnataka.gov.in
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Basin:
    """
    Describes a river basin for ARGUS deployment.
    Create from YAML config or programmatically.
    """

    basin_id: str
    display_name: str
    country: str
    bbox: tuple
    languages: List[str]
    data_sources: Dict[str, str]
    monsoon_months: List[int]
    flash_flood_hours: int

    # Optional — SDK will auto-configure if not provided
    state: Optional[str] = None
    states: Optional[List[str]] = None
    causal_dag: Optional[Dict[str, Any]] = None
    contact_authority: Optional[str] = None
    insurance_partners: Optional[List[str]] = None
    floodledger_enabled: bool = False
    chorus_enabled: bool = False
    oracle_villages: Optional[Any] = "auto"   # "auto" or list of village IDs

    @classmethod
    def from_config(cls, yaml_path: str) -> Basin:
        """
        Load basin configuration from a YAML file.

        Args:
            yaml_path: Path to the YAML configuration file.

        Returns:
            Basin instance configured from the YAML file.

        Example:
            basin = Basin.from_config("kaveri_karnataka.yaml")
        """
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        # Convert bbox list to tuple if necessary
        if isinstance(config.get("bbox"), list):
            config["bbox"] = tuple(config["bbox"])

        return cls(**config)

    @classmethod
    def from_registry(cls, basin_id: str) -> Basin:
        """
        Load a pre-configured basin from ARGUS Foundation registry.
        The registry contains validated configurations for known river basins.

        Args:
            basin_id: Registry identifier (e.g., "brahmaputra_assam",
                      "kaveri_karnataka", "mekong_vietnam")

        Returns:
            Basin instance from the registry.
        """
        import httpx

        registry_url = f"https://registry.argus.foundation/basins/{basin_id}.yaml"
        r = httpx.get(registry_url, timeout=30.0)
        r.raise_for_status()
        config = yaml.safe_load(r.text)

        if isinstance(config.get("bbox"), list):
            config["bbox"] = tuple(config["bbox"])

        return cls(**config)

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> Basin:
        """Create a Basin from a dictionary."""
        if isinstance(config.get("bbox"), list):
            config["bbox"] = tuple(config["bbox"])
        return cls(**config)

    def validate(self) -> List[str]:
        """
        Validate the basin configuration.
        Returns a list of warnings (empty = all valid).
        """
        warnings = []

        if len(self.bbox) != 4:
            warnings.append("bbox must have exactly 4 values: (west, south, east, north)")

        if not self.languages:
            warnings.append("At least one language code is required")

        if not self.data_sources:
            warnings.append("At least one data source is required")

        if not self.monsoon_months:
            warnings.append("monsoon_months must be specified")

        if self.flash_flood_hours < 1:
            warnings.append("flash_flood_hours must be >= 1")

        valid_sources = {
            "open_meteo", "cwc_wris", "copernicus", "era5",
            "bwdb", "vnmha", "mrc", "custom_api",
        }
        for source_type in self.data_sources.values():
            if source_type not in valid_sources:
                warnings.append(
                    f"Unknown data source type: {source_type}. "
                    f"Valid: {valid_sources}"
                )

        return warnings

    def to_yaml(self) -> str:
        """Serialize basin configuration to YAML string."""
        data = {
            "basin_id": self.basin_id,
            "display_name": self.display_name,
            "country": self.country,
            "bbox": list(self.bbox),
            "languages": self.languages,
            "data_sources": self.data_sources,
            "monsoon_months": self.monsoon_months,
            "flash_flood_hours": self.flash_flood_hours,
        }
        if self.state:
            data["state"] = self.state
        if self.states:
            data["states"] = self.states
        if self.causal_dag:
            data["causal_dag"] = self.causal_dag
        if self.contact_authority:
            data["contact_authority"] = self.contact_authority
        if self.insurance_partners:
            data["insurance_partners"] = self.insurance_partners
        if self.floodledger_enabled:
            data["floodledger_enabled"] = True
        if self.chorus_enabled:
            data["chorus_enabled"] = True
        if self.oracle_villages != "auto":
            data["oracle_villages"] = self.oracle_villages

        return yaml.dump(data, default_flow_style=False, allow_unicode=True)

    def __repr__(self) -> str:
        return (
            f"Basin(id={self.basin_id!r}, "
            f"country={self.country!r}, "
            f"languages={self.languages})"
        )
