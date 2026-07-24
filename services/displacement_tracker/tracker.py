"""
DisplacementTracker Service

The problem says: "Flash floods cause massive displacement."
ARGUS closes the loop: not just WHERE people are warned,
but WHERE they evacuated to, whether they arrived safely,
and how long they remain displaced.

This is the post-event accountability system -- it tracks
the human lifecycle of a flood:
  WARNED -> EVACUATING -> SHELTERED -> DISPLACED -> RETURNED

Data sources:
- RL Evacuation planner: initial route assignments
- Shelter registration (via CHORUS village reporter check-ins)
- NDRF field reports
- Village sarpanch WhatsApp confirmations
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class PersonStatus(str, Enum):
    AT_RISK = "AT_RISK"
    EVACUATING = "EVACUATING"
    SHELTERED = "SHELTERED"
    DISPLACED = "DISPLACED"           # Left the area permanently
    MISSING = "MISSING"               # Not accounted for
    RETURNED_HOME = "RETURNED_HOME"


class ShelterRegistration(BaseModel):
    shelter_id: str
    shelter_name: str
    location: str
    capacity: int
    current_occupancy: int = 0
    status: str = "OPEN"              # OPEN, FULL, CLOSED
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    available_capacity: int = 0


class VillageDisplacementStatus(BaseModel):
    village_id: str
    village_name: str
    total_population: int
    people_warned: int = 0
    people_evacuated: int = 0
    people_sheltered: int = 0
    people_missing: int = 0
    people_returned: int = 0
    assigned_shelter_id: Optional[str] = None
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# -- In-memory state (persisted to TimescaleDB in production) ---------------

shelter_registry: dict[str, ShelterRegistration] = {}
village_displacement: dict[str, VillageDisplacementStatus] = {}


def register_shelter(shelter: ShelterRegistration) -> dict:
    """Register a shelter centre for tracking during flood event."""
    shelter.available_capacity = shelter.capacity - shelter.current_occupancy
    shelter_registry[shelter.shelter_id] = shelter
    return {"registered": shelter.shelter_id, "capacity": shelter.capacity}


def update_village_displacement(update: VillageDisplacementStatus) -> dict:
    """
    Update displacement status for a village.
    Called by:
    - RL evacuation planner when evacuation is triggered
    - CHORUS bot when sarpanch sends shelter confirmation
    - NDRF field app when headcount at shelter complete
    """
    village_displacement[update.village_id] = update

    # Update shelter occupancy if assigned
    if update.assigned_shelter_id and update.assigned_shelter_id in shelter_registry:
        shelter = shelter_registry[update.assigned_shelter_id]
        shelter.current_occupancy = update.people_sheltered
        shelter.available_capacity = shelter.capacity - shelter.current_occupancy
        shelter.status = "FULL" if shelter.available_capacity <= 0 else "OPEN"
        shelter.last_updated = datetime.now(timezone.utc).isoformat()

    logger.info("Displacement updated",
                village=update.village_name,
                sheltered=update.people_sheltered,
                missing=update.people_missing)
    return {"updated": update.village_id}


def get_displacement_dashboard() -> dict:
    """
    Returns real-time displacement summary for the dashboard.
    This is what the DisplacementMap.jsx component displays.
    """
    total_warned = sum(v.people_warned for v in village_displacement.values())
    total_evacuated = sum(v.people_evacuated for v in village_displacement.values())
    total_sheltered = sum(v.people_sheltered for v in village_displacement.values())
    total_missing = sum(v.people_missing for v in village_displacement.values())
    total_returned = sum(v.people_returned for v in village_displacement.values())

    return {
        "summary": {
            "people_warned": total_warned,
            "people_evacuated": total_evacuated,
            "people_sheltered": total_sheltered,
            "people_missing": total_missing,
            "people_returned": total_returned,
            "evacuation_rate": round(total_evacuated / max(1, total_warned) * 100, 1),
            "shelter_rate": round(total_sheltered / max(1, total_evacuated) * 100, 1),
        },
        "shelters": [s.model_dump() for s in shelter_registry.values()],
        "villages": [v.model_dump() for v in village_displacement.values()],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def get_missing_persons_report() -> dict:
    """Returns villages with unaccounted people -- priority for search and rescue."""
    missing_villages = [
        v for v in village_displacement.values() if v.people_missing > 0
    ]
    missing_villages.sort(key=lambda v: v.people_missing, reverse=True)
    return {
        "total_missing": sum(v.people_missing for v in missing_villages),
        "villages_with_missing": [v.model_dump() for v in missing_villages],
        "ndrf_priority": [
            f"{v.village_name}: {v.people_missing} missing"
            for v in missing_villages[:5]
        ],
    }
