"""Tile provider for ScarNet satellite imagery display.

Provides free map tile URLs for satellite/terrain visualization.
No API keys required — all sources are open.

Tile Sources:
  - ESRI Satellite: High-res satellite imagery (ArcGIS World Imagery)
  - OpenStreetMap:  Standard street/terrain map
  - CartoDB Dark:   Dark theme for data overlays
  - OpenTopoMap:    Topographic contour map
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class TileSource:
    """A map tile source definition."""
    name: str
    url: str
    attribution: str
    max_zoom: int = 19
    subdomains: str = "abc"


# ── Available Tile Sources (all free, no API keys) ────────────────────────

TILE_SOURCES: Dict[str, TileSource] = {
    "satellite": TileSource(
        name="ESRI Satellite",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attribution="&copy; Esri, Maxar, Earthstar Geographics",
        max_zoom=18,
        subdomains="",
    ),
    "osm": TileSource(
        name="OpenStreetMap",
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution="&copy; OpenStreetMap contributors",
        max_zoom=19,
    ),
    "dark": TileSource(
        name="CartoDB Dark",
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attribution="&copy; OpenStreetMap contributors &copy; CARTO",
        max_zoom=20,
    ),
    "topo": TileSource(
        name="OpenTopoMap",
        url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution="&copy; OpenStreetMap contributors, SRTM | &copy; OpenTopoMap",
        max_zoom=17,
    ),
}

# Default tile source for ScarNet satellite view
DEFAULT_TILE_SOURCE = "satellite"


def get_tile_url(source: str = DEFAULT_TILE_SOURCE) -> str:
    """Get tile URL template for given source name.

    Args:
        source: One of 'satellite', 'osm', 'dark', 'topo'

    Returns:
        URL template string with {z}/{x}/{y} placeholders.
    """
    tile = TILE_SOURCES.get(source, TILE_SOURCES[DEFAULT_TILE_SOURCE])
    return tile.url


def get_tile_attribution(source: str = DEFAULT_TILE_SOURCE) -> str:
    """Get attribution string for given source."""
    tile = TILE_SOURCES.get(source, TILE_SOURCES[DEFAULT_TILE_SOURCE])
    return tile.attribution


def get_all_sources() -> Dict[str, dict]:
    """Return all available tile sources as serializable dict."""
    return {
        key: {
            "name": src.name,
            "url": src.url,
            "attribution": src.attribution,
            "max_zoom": src.max_zoom,
        }
        for key, src in TILE_SOURCES.items()
    }
