"""Sentinel-1/2 satellite imagery client.

Provides access to Sentinel-2 multispectral (10m, 13 bands, 5-day revisit) and
Sentinel-1 SAR (cloud-penetrating, 6-12 day revisit) imagery.

Data Sources (priority order):
  1. DEMO_MODE (default)  - synthetic GeoTIFF tiles, always works offline
  2. NASA Earthdata       - HLSL30 (Harmonized Landsat-Sentinel, 30m, free token)
  3. AWS Open Data        - sentinel-s2-l2a S3 bucket (no auth, requester-pays)

No Copernicus / MapBox dependencies.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Demo tile locations
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SENTINEL2_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "sentinel2"

# NASA Earthdata endpoints
NASA_EARTHDATA_TOKEN_URL = "https://urs.earthdata.nasa.gov/api/users/token"
NASA_CMR_SEARCH_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
NASA_HLSL30_COLLECTION = "C2021957657-LPCLOUD"

# AWS Open Data Sentinel-2 bucket
AWS_SENTINEL2_BUCKET = "sentinel-s2-l2a"
AWS_SENTINEL2_REGION = "eu-central-1"


class SentinelClient:
    """Client for Sentinel-1/2 satellite imagery.

    Supports three data sources in priority order:
      1. Demo mode   - pre-generated synthetic tiles (default, offline-safe)
      2. NASA Earthdata - free HLSL30 data via CMR API
      3. AWS Open Data  - Sentinel-2 L2A from public S3 bucket

    In demo mode, returns pre-generated synthetic tiles.
    """

    def __init__(
        self,
        nasa_token: str = "",
        aws_bucket: str = AWS_SENTINEL2_BUCKET,
        demo_mode: bool = True,
    ):
        self.demo_mode = demo_mode
        self.nasa_token = nasa_token
        self.aws_bucket = aws_bucket
        self.session_token: Optional[str] = None

        if not demo_mode and nasa_token:
            try:
                self._validate_nasa_token(nasa_token)
                logger.info("sentinel_authenticated", api="nasa_earthdata")
            except Exception as e:
                logger.warning("sentinel_auth_failed", error=str(e))
                self.demo_mode = True
        else:
            logger.info("sentinel_demo_mode", reason="no credentials or demo_mode=True")

    # -- Authentication -------------------------------------------------------

    def _validate_nasa_token(self, token: str) -> None:
        """Validate NASA Earthdata bearer token.

        Tokens are created at https://urs.earthdata.nasa.gov and are
        long-lived (90 days). We just verify we can hit the CMR API.
        """
        try:
            import httpx

            resp = httpx.get(
                NASA_CMR_SEARCH_URL,
                params={
                    "collection_concept_id": NASA_HLSL30_COLLECTION,
                    "page_size": 1,
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            self.session_token = token
        except Exception as e:
            raise RuntimeError(f"NASA Earthdata auth failed: {e}") from e

    # -- Download Methods ------------------------------------------------------

    def download_sentinel2_tile(
        self,
        bbox: tuple,
        date_from: datetime,
        date_to: datetime,
        max_cloud_pct: float = 20.0,
    ) -> Optional[str]:
        """Download least-cloudy Sentinel-2 L2A tile for bbox and date range.

        Priority: Demo tiles -> NASA HLSL30 -> AWS S3 Open Data.

        Returns: local file path to downloaded tile (or None if unavailable).
        """
        if self.demo_mode:
            logger.info("sentinel2_demo_download", bbox=bbox)
            return str(self._get_demo_before_path())

        # Try NASA Earthdata CMR search
        if self.session_token:
            result = self._search_nasa_hlsl30(bbox, date_from, date_to, max_cloud_pct)
            if result:
                return result

        # Fallback: AWS Open Data S3
        result = self._search_aws_sentinel2(bbox, date_from, date_to)
        if result:
            return result

        logger.warning(
            "sentinel2_no_data",
            bbox=bbox,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )
        return None

    def download_sentinel1_sar(
        self, bbox: tuple, date: datetime
    ) -> Optional[str]:
        """Download Sentinel-1 GRD SAR tile (flood extent confirmation).

        Returns: local file path to downloaded tile.
        """
        if self.demo_mode:
            logger.info("sentinel1_demo_download", bbox=bbox)
            sar_path = _SENTINEL2_DIR / "beas_valley_2023_08_flood_sar.npy"
            return str(sar_path) if sar_path.exists() else None

        logger.info("sentinel1_download", bbox=bbox, date=date.isoformat())
        return None

    # -- NASA Earthdata Methods ------------------------------------------------

    def _search_nasa_hlsl30(
        self,
        bbox: tuple,
        date_from: datetime,
        date_to: datetime,
        max_cloud_pct: float = 20.0,
    ) -> Optional[str]:
        """Search NASA CMR for HLSL30 (Harmonized Landsat-Sentinel) granules.

        Args:
            bbox: (west, south, east, north) in EPSG:4326
            date_from: start of temporal window
            date_to: end of temporal window
            max_cloud_pct: maximum cloud cover percentage

        Returns: local path to downloaded tile, or None.
        """
        try:
            import httpx

            west, south, east, north = bbox
            temporal = (
                f"{date_from.strftime('%Y-%m-%dT00:00:00Z')},"
                f"{date_to.strftime('%Y-%m-%dT23:59:59Z')}"
            )

            resp = httpx.get(
                NASA_CMR_SEARCH_URL,
                params={
                    "collection_concept_id": NASA_HLSL30_COLLECTION,
                    "bounding_box": f"{west},{south},{east},{north}",
                    "temporal": temporal,
                    "cloud_cover": f"0,{max_cloud_pct}",
                    "sort_key": "cloud_cover",
                    "page_size": 5,
                },
                headers={"Authorization": f"Bearer {self.session_token}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            entries = resp.json().get("feed", {}).get("entry", [])

            if not entries:
                logger.info("nasa_hlsl30_no_results", bbox=bbox)
                return None

            # Pick best granule (lowest cloud cover, first in sorted results)
            granule = entries[0]
            download_url = None
            for link in granule.get("links", []):
                if link.get("rel") == "http://esipfed.org/ns/fedsearch/1.1/data#":
                    download_url = link["href"]
                    break

            if download_url:
                logger.info(
                    "nasa_hlsl30_found",
                    granule_id=granule.get("id"),
                    cloud_cover=granule.get("cloud_cover"),
                    url=download_url,
                )
                return self._download_granule(download_url)

            return None

        except Exception as e:
            logger.warning("nasa_hlsl30_search_failed", error=str(e))
            return None

    def _download_granule(self, url: str) -> Optional[str]:
        """Download a granule from NASA Earthdata to local cache."""
        try:
            import httpx

            cache_dir = _SENTINEL2_DIR / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)

            filename = url.split("/")[-1]
            local_path = cache_dir / filename

            if local_path.exists():
                logger.info("granule_cached", path=str(local_path))
                return str(local_path)

            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.session_token}"},
                timeout=60.0,
                follow_redirects=True,
            )
            resp.raise_for_status()

            local_path.write_bytes(resp.content)
            logger.info("granule_downloaded", path=str(local_path), size=len(resp.content))
            return str(local_path)

        except Exception as e:
            logger.warning("granule_download_failed", url=url, error=str(e))
            return None

    # -- AWS Open Data Methods -------------------------------------------------

    def _search_aws_sentinel2(
        self,
        bbox: tuple,
        date_from: datetime,
        date_to: datetime,
    ) -> Optional[str]:
        """Search AWS Open Data Sentinel-2 L2A bucket.

        The sentinel-s2-l2a bucket is organized as:
          s3://sentinel-s2-l2a/tiles/{utm_zone}/{lat_band}/{grid_sq}/{year}/{month}/{day}/

        No authentication required (requester-pays).

        Returns: local path to downloaded tile, or None.
        """
        try:
            logger.info(
                "aws_sentinel2_search",
                bucket=self.aws_bucket,
                bbox=bbox,
                date_from=date_from.isoformat(),
            )
            # AWS S3 listing would require boto3 - for now log intent
            # Full implementation would use boto3 to list and download
            return None

        except Exception as e:
            logger.warning("aws_sentinel2_search_failed", error=str(e))
            return None

    # -- Demo Tiles ------------------------------------------------------------

    def get_demo_tiles(self) -> dict:
        """Return paths to pre-generated demo tiles (Beas Valley, Himachal Pradesh).

        These are generated by scripts/generate_synthetic_sentinel_tiles.py
        and committed to data/sentinel2/.

        CRITICAL: demo must never depend on live satellite download.
        """
        before = self._get_demo_before_path()
        after = self._get_demo_after_path()
        sar = _SENTINEL2_DIR / "beas_valley_2023_08_flood_sar.npy"

        return {
            "before": str(before) if before.exists() else None,
            "after": str(after) if after.exists() else None,
            "sar_flood": str(sar) if sar.exists() else None,
            "before_date": "2022-08-15",
            "after_date": "2023-09-15",
            "location": "Beas Valley, Himachal Pradesh",
            "bbox": (77.05, 31.80, 77.30, 32.05),
        }

    def _get_demo_before_path(self) -> Path:
        """Resolve before tile path, trying .tif then .npy."""
        tif = _SENTINEL2_DIR / "beas_valley_2022_08_before.tif"
        npy = _SENTINEL2_DIR / "beas_valley_2022_08_before.npy"
        return tif if tif.exists() else npy

    def _get_demo_after_path(self) -> Path:
        """Resolve after tile path, trying .tif then .npy."""
        tif = _SENTINEL2_DIR / "beas_valley_2023_09_after.tif"
        npy = _SENTINEL2_DIR / "beas_valley_2023_09_after.npy"
        return tif if tif.exists() else npy

    def tiles_available(self) -> bool:
        """Check if demo tiles have been generated."""
        tiles = self.get_demo_tiles()
        return tiles["before"] is not None and tiles["after"] is not None
