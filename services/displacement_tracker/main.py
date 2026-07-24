"""Displacement Tracker -- Port 8024.

Tracks displaced populations, shelter occupancy, and relief distribution
during and after flood events. Provides real-time shelter capacity data
to the Evacuation RL service and displacement flow visualisation to the
dashboard.

Gap 8 closure: Problem statement asks about post-disaster response.
ARGUS had prediction + evacuation but no displacement tracking.
"""

from __future__ import annotations

import json
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.displacement_tracker.tracker import (
    ShelterRegistration,
    VillageDisplacementStatus,
    register_shelter as engine_register_shelter,
    update_village_displacement,
    get_displacement_dashboard,
    get_missing_persons_report,
    shelter_registry as engine_shelter_registry,
    village_displacement as engine_village_displacement,
)

logger = structlog.get_logger(__name__)

# -- Configuration --------------------------------------------------------
DISP_PORT = int(os.getenv("DISPLACEMENT_TRACKER_PORT", "8024"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")


# -- Data Models ----------------------------------------------------------


class Shelter(BaseModel):
    shelter_id: str
    name: str
    district: str
    latitude: float
    longitude: float
    capacity: int
    current_occupancy: int = 0
    status: str = "OPEN"  # OPEN, FULL, CLOSED, STANDBY
    amenities: List[str] = []
    contact_phone: str = ""
    last_updated: str = ""


class DisplacedGroup(BaseModel):
    group_id: str
    origin_village: str
    origin_district: str
    destination_shelter_id: str
    people_count: int
    children_count: int = 0
    elderly_count: int = 0
    medical_needs: int = 0
    status: str = "IN_TRANSIT"  # REGISTERED, IN_TRANSIT, SHELTERED, RETURNED
    registered_at: str = ""
    arrived_at: Optional[str] = None


class ReliefDistribution(BaseModel):
    distribution_id: str
    shelter_id: str
    items: Dict[str, int]  # {"food_packets": 500, "water_litres": 1000, ...}
    distributed_at: str
    beneficiaries: int


# -- In-memory state ------------------------------------------------------

_shelters: Dict[str, Shelter] = {}
_displaced_groups: Dict[str, DisplacedGroup] = {}
_relief_log: List[ReliefDistribution] = []
_stats = {
    "total_displaced": 0,
    "currently_sheltered": 0,
    "returned_home": 0,
    "shelters_active": 0,
    "relief_distributions": 0,
}


# -- Lifespan -------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("displacement_tracker_starting", port=DISP_PORT, demo_mode=DEMO_MODE)

    if DEMO_MODE:
        _seed_demo_data()

    logger.info("displacement_tracker_ready",
                shelters=len(_shelters),
                displaced=_stats["total_displaced"])
    yield
    logger.info("displacement_tracker_shutdown")


app = FastAPI(
    title="ARGUS Displacement Tracker",
    version="1.0.0",
    description="Post-event displacement tracking, shelter occupancy, relief distribution",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Helpers ---------------------------------------------------------------


def _seed_demo_data():
    """Seed Brahmaputra basin shelters and displacement data."""
    now = datetime.now(timezone.utc)

    shelters = [
        Shelter(
            shelter_id="SHELTER_NIMATI", name="Nimati High School",
            district="Majuli", latitude=26.95, longitude=94.25,
            capacity=500, current_occupancy=387,
            status="OPEN",
            amenities=["drinking_water", "medical_camp", "food_distribution"],
            contact_phone="03775-222111",
            last_updated=now.isoformat(),
        ),
        Shelter(
            shelter_id="SHELTER_JORHAT", name="Jorhat Community Hall",
            district="Jorhat", latitude=26.75, longitude=94.20,
            capacity=800, current_occupancy=612,
            status="OPEN",
            amenities=["drinking_water", "medical_camp", "food_distribution",
                        "sanitation", "child_care"],
            contact_phone="03771-320555",
            last_updated=now.isoformat(),
        ),
        Shelter(
            shelter_id="SHELTER_GOLAGHAT", name="Golaghat Relief Camp",
            district="Golaghat", latitude=26.52, longitude=93.96,
            capacity=400, current_occupancy=89,
            status="OPEN",
            amenities=["drinking_water", "medical_camp"],
            contact_phone="03774-281333",
            last_updated=now.isoformat(),
        ),
        Shelter(
            shelter_id="SHELTER_KULLU", name="Kullu Relief Camp",
            district="Kullu", latitude=31.96, longitude=77.11,
            capacity=300, current_occupancy=145,
            status="OPEN",
            amenities=["drinking_water", "food_distribution", "blankets"],
            contact_phone="01902-222111",
            last_updated=now.isoformat(),
        ),
    ]

    for s in shelters:
        _shelters[s.shelter_id] = s
        _stats["shelters_active"] += 1

    groups = [
        DisplacedGroup(
            group_id="GRP_MAJULI_W7", origin_village="Majuli Ward 7",
            origin_district="Majuli",
            destination_shelter_id="SHELTER_NIMATI",
            people_count=387, children_count=92, elderly_count=41,
            medical_needs=8, status="SHELTERED",
            registered_at=(now - timedelta(hours=18)).isoformat(),
            arrived_at=(now - timedelta(hours=16)).isoformat(),
        ),
        DisplacedGroup(
            group_id="GRP_MAJULI_W12", origin_village="Majuli Ward 12",
            origin_district="Majuli",
            destination_shelter_id="SHELTER_JORHAT",
            people_count=612, children_count=156, elderly_count=78,
            medical_needs=15, status="SHELTERED",
            registered_at=(now - timedelta(hours=14)).isoformat(),
            arrived_at=(now - timedelta(hours=12)).isoformat(),
        ),
        DisplacedGroup(
            group_id="GRP_KAMALABARI", origin_village="Kamalabari",
            origin_district="Majuli",
            destination_shelter_id="SHELTER_GOLAGHAT",
            people_count=89, children_count=23, elderly_count=12,
            medical_needs=3, status="SHELTERED",
            registered_at=(now - timedelta(hours=10)).isoformat(),
            arrived_at=(now - timedelta(hours=8)).isoformat(),
        ),
        DisplacedGroup(
            group_id="GRP_KULLU", origin_village="Kullu Town",
            origin_district="Kullu",
            destination_shelter_id="SHELTER_KULLU",
            people_count=145, children_count=34, elderly_count=18,
            medical_needs=5, status="SHELTERED",
            registered_at=(now - timedelta(hours=6)).isoformat(),
            arrived_at=(now - timedelta(hours=4)).isoformat(),
        ),
    ]

    for g in groups:
        _displaced_groups[g.group_id] = g
        _stats["total_displaced"] += g.people_count
        _stats["currently_sheltered"] += g.people_count

    # Seed some relief distributions
    _relief_log.append(ReliefDistribution(
        distribution_id="RELIEF_001",
        shelter_id="SHELTER_NIMATI",
        items={"food_packets": 500, "water_litres": 2000, "blankets": 200,
               "medical_kits": 20},
        distributed_at=(now - timedelta(hours=6)).isoformat(),
        beneficiaries=387,
    ))
    _relief_log.append(ReliefDistribution(
        distribution_id="RELIEF_002",
        shelter_id="SHELTER_JORHAT",
        items={"food_packets": 800, "water_litres": 3000, "blankets": 350,
               "medical_kits": 30, "sanitary_kits": 100},
        distributed_at=(now - timedelta(hours=4)).isoformat(),
        beneficiaries=612,
    ))
    _stats["relief_distributions"] = 2


# -- API Endpoints ---------------------------------------------------------


@app.get("/api/v1/displacement/shelters")
async def get_shelters(district: Optional[str] = None):
    """Return all shelters with current occupancy."""
    shelters = list(_shelters.values())
    if district:
        shelters = [s for s in shelters if s.district.lower() == district.lower()]
    return {
        "total": len(shelters),
        "shelters": [s.model_dump() for s in shelters],
    }


@app.get("/api/v1/displacement/shelter/{shelter_id}")
async def get_shelter(shelter_id: str):
    """Return a specific shelter's details."""
    if shelter_id not in _shelters:
        raise HTTPException(404, f"Shelter not found: {shelter_id}")
    return _shelters[shelter_id].model_dump()


@app.get("/api/v1/displacement/groups")
async def get_displaced_groups(status: Optional[str] = None):
    """Return all displaced groups."""
    groups = list(_displaced_groups.values())
    if status:
        groups = [g for g in groups if g.status == status.upper()]
    return {
        "total_groups": len(groups),
        "total_people": sum(g.people_count for g in groups),
        "groups": [g.model_dump() for g in groups],
    }


@app.get("/api/v1/displacement/summary")
async def get_displacement_summary():
    """Return high-level displacement summary."""
    return {
        "total_displaced": _stats["total_displaced"],
        "currently_sheltered": _stats["currently_sheltered"],
        "returned_home": _stats["returned_home"],
        "shelters_active": _stats["shelters_active"],
        "shelter_capacity_used_pct": round(
            sum(s.current_occupancy for s in _shelters.values())
            / max(1, sum(s.capacity for s in _shelters.values())) * 100, 1
        ),
        "children_displaced": sum(
            g.children_count for g in _displaced_groups.values()
        ),
        "elderly_displaced": sum(
            g.elderly_count for g in _displaced_groups.values()
        ),
        "medical_needs": sum(
            g.medical_needs for g in _displaced_groups.values()
        ),
        "relief_distributions": _stats["relief_distributions"],
    }


@app.get("/api/v1/displacement/flows")
async def get_displacement_flows():
    """Return displacement flows for visualisation (origin -> shelter)."""
    flows = []
    for g in _displaced_groups.values():
        shelter = _shelters.get(g.destination_shelter_id)
        if shelter:
            flows.append({
                "origin": g.origin_village,
                "origin_district": g.origin_district,
                "destination": shelter.name,
                "destination_lat": shelter.latitude,
                "destination_lon": shelter.longitude,
                "people_count": g.people_count,
                "status": g.status,
            })
    return {"flows": flows}


@app.get("/api/v1/displacement/relief")
async def get_relief_log():
    """Return relief distribution log."""
    return {
        "total_distributions": len(_relief_log),
        "distributions": [r.model_dump() for r in _relief_log],
    }


@app.post("/api/v1/displacement/register-group")
async def register_group(group: DisplacedGroup):
    """Register a new displaced group."""
    group.registered_at = datetime.now(timezone.utc).isoformat()
    _displaced_groups[group.group_id] = group
    _stats["total_displaced"] += group.people_count

    # Update shelter occupancy
    if group.destination_shelter_id in _shelters:
        _shelters[group.destination_shelter_id].current_occupancy += group.people_count

    logger.info("displaced_group_registered",
                group_id=group.group_id,
                people=group.people_count)
    return {"status": "REGISTERED", "group": group.model_dump()}


# -- Tracker engine endpoints (tracker.py) ---------------------------------


@app.post("/api/v1/displacement/shelter/register")
async def api_register_shelter(shelter: ShelterRegistration):
    """Register a shelter centre for tracking during flood event."""
    return engine_register_shelter(shelter)


@app.post("/api/v1/displacement/village/update")
async def api_update_village(update: VillageDisplacementStatus):
    """Update displacement status for a village."""
    return update_village_displacement(update)


@app.get("/api/v1/displacement/dashboard")
async def api_displacement_dashboard():
    """Returns real-time displacement summary for the dashboard."""
    return get_displacement_dashboard()


@app.get("/api/v1/displacement/missing-persons")
async def api_missing_persons():
    """Returns villages with unaccounted people -- priority for S&R."""
    return get_missing_persons_report()


@app.get("/health")
async def health():
    return {
        "service": "displacement_tracker",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_mode": DEMO_MODE,
        "shelters_active": _stats["shelters_active"],
        "total_displaced": _stats["total_displaced"],
        "currently_sheltered": _stats["currently_sheltered"],
    }


if __name__ == "__main__":
    uvicorn.run("services.displacement_tracker.main:app", host="0.0.0.0",
                port=DISP_PORT, reload=True)
