#!/usr/bin/env python3
"""Generate synthetic Sentinel-2 GeoTIFFs for ScarNet demo.

Creates two synthetic 13-band Sentinel-2 tiles simulating
Beas Valley, Himachal Pradesh — before and after deforestation.

These are ~2MB each (256×256 pixels at 10m resolution) and
contain realistic NDVI, NDWI, NDBI spectral index patterns.

Usage:
    python scripts/generate_synthetic_sentinel_tiles.py
"""

from __future__ import annotations

import os
import sys
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sentinel2")

# Sentinel-2 band info (13 bands)
# B1=Coastal, B2=Blue, B3=Green, B4=Red, B5-B7=RedEdge, B8=NIR, B8A=NarrowNIR,
# B9=WaterVapour, B10=Cirrus, B11=SWIR1, B12=SWIR2, plus B13 placeholder
BANDS = 13
WIDTH, HEIGHT = 256, 256

# Beas Valley approximate bounds (for metadata)
BBOX = (77.05, 31.80, 77.30, 32.05)  # min_lon, min_lat, max_lon, max_lat


def _make_terrain_mask(w: int, h: int, seed: int = 42) -> dict:
    """Create spatial masks for forest, river, urban, bare soil."""
    rng = np.random.RandomState(seed)

    # River: vertical band with some meander
    river = np.zeros((h, w), dtype=bool)
    cx = w // 2
    for row in range(h):
        meander = int(15 * np.sin(row / 30.0))
        left = max(0, cx + meander - 8)
        right = min(w, cx + meander + 8)
        river[row, left:right] = True

    # Forest: everything except river by default (before image)
    forest = ~river

    # Urban: small patch in bottom-right
    urban = np.zeros((h, w), dtype=bool)
    urban[h - 50 : h, w - 60 : w] = True
    forest[urban] = False

    # Slope: left side of image (simulated hillside)
    slope = np.zeros((h, w), dtype=bool)
    slope[:, : w // 4] = True

    return {"river": river, "forest": forest, "urban": urban, "slope": slope, "rng": rng}


def _generate_tile(masks: dict, deforested: bool = False, urbanized: bool = False) -> np.ndarray:
    """Generate a 13-band synthetic Sentinel-2 tile."""
    rng = masks["rng"]
    data = np.zeros((BANDS, HEIGHT, WIDTH), dtype=np.float32)

    # Base reflectance (scaled 0-10000 like real S2 L2A)
    for b in range(BANDS):
        data[b] = 500 + rng.normal(0, 30, (HEIGHT, WIDTH))

    forest = masks["forest"].copy()
    river = masks["river"]
    urban = masks["urban"].copy()

    # Simulate deforestation: remove forest in top-left quadrant
    if deforested:
        defor_zone = np.zeros_like(forest)
        defor_zone[20:120, 30:100] = True
        forest[defor_zone] = False

    # Simulate urbanization: expand urban area
    if urbanized:
        urban_expand = np.zeros_like(urban)
        urban_expand[HEIGHT - 80 : HEIGHT, WIDTH - 90 : WIDTH] = True
        urban[urban_expand] = True
        forest[urban] = False

    # ── Forest pixels ────────────────────────────────────
    # High NIR (B8), low Red (B4), moderate Green (B3)
    data[3][forest] = 400 + rng.normal(0, 20, forest.sum())    # B4 Red — low
    data[2][forest] = 800 + rng.normal(0, 30, forest.sum())    # B3 Green
    data[7][forest] = 3500 + rng.normal(0, 100, forest.sum())  # B8 NIR — high
    data[10][forest] = 1200 + rng.normal(0, 50, forest.sum())  # B11 SWIR1

    # ── River pixels ─────────────────────────────────────
    # High Green, low NIR (water absorbs NIR)
    data[2][river] = 1200 + rng.normal(0, 40, river.sum())     # B3 Green
    data[7][river] = 300 + rng.normal(0, 20, river.sum())      # B8 NIR — low
    data[3][river] = 600 + rng.normal(0, 25, river.sum())      # B4 Red

    # ── Urban pixels ─────────────────────────────────────
    # Low NIR, low Green, moderate SWIR
    data[3][urban] = 1500 + rng.normal(0, 50, urban.sum())     # B4 Red
    data[7][urban] = 1800 + rng.normal(0, 60, urban.sum())     # B8 NIR — moderate
    data[10][urban] = 2500 + rng.normal(0, 80, urban.sum())    # B11 SWIR1 — high
    data[2][urban] = 1000 + rng.normal(0, 40, urban.sum())     # B3 Green

    # ── Bare soil (deforested areas) ─────────────────────
    if deforested:
        bare = ~forest & ~river & ~urban
        data[3][bare] = 1800 + rng.normal(0, 60, bare.sum())   # B4 Red — high
        data[7][bare] = 2000 + rng.normal(0, 80, bare.sum())   # B8 NIR — moderate
        data[2][bare] = 1400 + rng.normal(0, 50, bare.sum())   # B3 Green

    # Clip to valid range
    data = np.clip(data, 0, 10000)

    return data


def save_as_npy(data: np.ndarray, filepath: str, metadata: dict | None = None):
    """Save as .npy file (works without rasterio)."""
    np.save(filepath, data)
    # Save metadata alongside
    if metadata:
        import json
        meta_path = filepath.replace(".npy", "_meta.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)


def save_as_tif(data: np.ndarray, filepath: str):
    """Save as GeoTIFF using rasterio (if available)."""
    try:
        import rasterio
        from rasterio.transform import from_bounds

        transform = from_bounds(*BBOX, WIDTH, HEIGHT)
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "width": WIDTH,
            "height": HEIGHT,
            "count": BANDS,
            "crs": "EPSG:4326",
            "transform": transform,
            "compress": "lzw",
        }
        with rasterio.open(filepath, "w", **profile) as dst:
            for i in range(BANDS):
                dst.write(data[i], i + 1)
        return True
    except ImportError:
        return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    masks = _make_terrain_mask(WIDTH, HEIGHT, seed=42)

    # ── Before tile (2022-08, pristine) ──────────────────
    print("Generating BEFORE tile (Beas Valley 2022-08, pristine)...")
    before = _generate_tile(masks, deforested=False, urbanized=False)

    # ── After tile (2023-09, degraded) ───────────────────
    print("Generating AFTER tile (Beas Valley 2023-09, post-deforestation)...")
    masks_after = _make_terrain_mask(WIDTH, HEIGHT, seed=42)
    after = _generate_tile(masks_after, deforested=True, urbanized=True)

    meta_before = {
        "source": "synthetic", "location": "Beas Valley, Himachal Pradesh",
        "date": "2022-08-15", "satellite": "Sentinel-2A (simulated)",
        "resolution_m": 10, "bands": 13, "bbox": list(BBOX),
    }
    meta_after = {
        **meta_before, "date": "2023-09-15",
        "notes": "Post-deforestation + urbanization expansion",
    }

    # Try GeoTIFF first, fall back to .npy
    before_tif = os.path.join(OUTPUT_DIR, "beas_valley_2022_08_before.tif")
    after_tif = os.path.join(OUTPUT_DIR, "beas_valley_2023_09_after.tif")

    if save_as_tif(before, before_tif) and save_as_tif(after, after_tif):
        print(f"  ✅ Saved GeoTIFF: {before_tif}")
        print(f"  ✅ Saved GeoTIFF: {after_tif}")
    else:
        # Fallback: save as .npy
        before_npy = os.path.join(OUTPUT_DIR, "beas_valley_2022_08_before.npy")
        after_npy = os.path.join(OUTPUT_DIR, "beas_valley_2023_09_after.npy")
        save_as_npy(before, before_npy, meta_before)
        save_as_npy(after, after_npy, meta_after)
        print(f"  ✅ Saved NumPy: {before_npy}")
        print(f"  ✅ Saved NumPy: {after_npy}")
        print("  ℹ️  Install rasterio for GeoTIFF format: pip install rasterio")

    # ── SAR flood tile (simple binary) ───────────────────
    print("Generating SAR flood extent tile...")
    sar = np.zeros((1, HEIGHT, WIDTH), dtype=np.float32)
    sar[0][masks["river"]] = 1.0
    # Expand flood extent beyond normal river bounds
    from scipy.ndimage import binary_dilation
    sar[0] = binary_dilation(sar[0] > 0.5, iterations=5).astype(np.float32)
    sar_path = os.path.join(OUTPUT_DIR, "beas_valley_2023_08_flood_sar.npy")
    np.save(sar_path, sar)
    print(f"  ✅ Saved SAR flood: {sar_path}")

    print("\nSynthetic tiles ready for ScarNet demo! 🛰️")


if __name__ == "__main__":
    main()
