"""
Multi-Basin Manager — Cross-basin coordination and data aggregation.
Port: 8015

Manages multiple river basins (Brahmaputra, Beas, Godavari),
aggregates predictions, and provides basin-level APIs.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("multi_basin")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

PORT = int(os.getenv("MULTI_BASIN_PORT", "8015"))

# ── Basin definitions ──────────────────────────────────────────
BASINS = {
    "brahmaputra": {
        "id": "brahmaputra",
        "name": "Brahmaputra Basin",
        "region": "Northeast India",
        "states": ["Assam", "Arunachal Pradesh", "Meghalaya"],
        "center": [26.1, 91.7],
        "area_km2": 580_000,
        "stations": [],
    },
    "beas": {
        "id": "beas",
        "name": "Beas Basin",
        "region": "Himachal Pradesh",
        "states": ["Himachal Pradesh", "Punjab"],
        "center": [31.9, 77.1],
        "area_km2": 20_303,
        "stations": [],
    },
    "godavari": {
        "id": "godavari",
        "name": "Godavari Basin",
        "region": "Central–South India",
        "states": ["Maharashtra", "Telangana", "Andhra Pradesh"],
        "center": [19.0, 79.5],
        "area_km2": 312_812,
        "stations": [],
    },
}

# ── In-memory village registry ─────────────────────────────────
VILLAGES = [
    {"id": "v001", "name": "Majuli Island", "district": "Jorhat", "basin": "brahmaputra", "lat": 26.95, "lon": 94.17},
    {"id": "v002", "name": "Dhubri Town", "district": "Dhubri", "basin": "brahmaputra", "lat": 26.02, "lon": 89.98},
    {"id": "v003", "name": "Kaziranga", "district": "Golaghat", "basin": "brahmaputra", "lat": 26.58, "lon": 93.17},
    {"id": "v004", "name": "Tezpur", "district": "Sonitpur", "basin": "brahmaputra", "lat": 26.63, "lon": 92.80},
    {"id": "v005", "name": "Dibrugarh", "district": "Dibrugarh", "basin": "brahmaputra", "lat": 27.47, "lon": 94.91},
    {"id": "v006", "name": "Kullu Town", "district": "Kullu", "basin": "beas", "lat": 31.96, "lon": 77.11},
    {"id": "v007", "name": "Manali", "district": "Kullu", "basin": "beas", "lat": 32.24, "lon": 77.19},
    {"id": "v008", "name": "Mandi", "district": "Mandi", "basin": "beas", "lat": 31.72, "lon": 76.93},
    {"id": "v009", "name": "Nashik", "district": "Nashik", "basin": "godavari", "lat": 19.99, "lon": 73.79},
    {"id": "v010", "name": "Nanded", "district": "Nanded", "basin": "godavari", "lat": 19.16, "lon": 77.30},
    {"id": "v011", "name": "Rajahmundry", "district": "East Godavari", "basin": "godavari", "lat": 17.00, "lon": 81.80},
    {"id": "v012", "name": "Bhadrachalam", "district": "Khammam", "basin": "godavari", "lat": 17.67, "lon": 80.89},
]


# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="ARGUS Multi-Basin Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "service": "multi_basin",
        "status": "healthy",
        "basins": list(BASINS.keys()),
        "total_villages": len(VILLAGES),
    }


@app.get("/basins")
async def list_basins():
    """List all monitored basins."""
    return {"basins": list(BASINS.values())}


@app.get("/basins/{basin_id}")
async def get_basin(basin_id: str):
    """Get details for a specific basin."""
    basin = BASINS.get(basin_id)
    if not basin:
        return {"error": f"Basin '{basin_id}' not found"}, 404
    villages = [v for v in VILLAGES if v["basin"] == basin_id]
    return {**basin, "villages": villages, "village_count": len(villages)}


@app.get("/evacuation/villages")
async def list_villages(basin: Optional[str] = Query(None)):
    """List villages, optionally filtered by basin."""
    if basin:
        filtered = [v for v in VILLAGES if v["basin"] == basin]
    else:
        filtered = VILLAGES
    return {"villages": filtered}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
