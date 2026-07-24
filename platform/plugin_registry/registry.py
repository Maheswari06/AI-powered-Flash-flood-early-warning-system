"""ARGUS Plugin Registry — Community plugins, basin configs, and extensions.

Provides a registry for community-contributed:
  - Basin configurations (YAML)
  - Model plugins (custom prediction models)
  - Alert channel plugins (new notification channels)
  - Data source adapters (gauge networks, satellite feeds)

Endpoints:
  GET  /api/v1/registry/plugins          → List all plugins
  GET  /api/v1/registry/plugins/{id}     → Get plugin details
  POST /api/v1/registry/plugins          → Submit a plugin
  GET  /api/v1/registry/plugins/search   → Search plugins
  GET  /api/v1/registry/stats            → Registry statistics
  GET  /health                           → Liveness check

Run: ``uvicorn platform.plugin_registry.registry:app --reload --port 5176``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="ARGUS Plugin Registry",
    description="Community plugins, basin configs, and extensions for ARGUS",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Enums & Models ──────────────────────────────────────────────────────

class PluginType(str, Enum):
    BASIN_CONFIG = "basin_config"
    MODEL = "model"
    ALERT_CHANNEL = "alert_channel"
    DATA_SOURCE = "data_source"
    VISUALIZATION = "visualization"


class PluginStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class PluginSubmission(BaseModel):
    """Schema for plugin submission."""
    name: str = Field(..., min_length=3, max_length=100)
    plugin_type: PluginType
    description: str = Field(..., min_length=10, max_length=1000)
    author: str = Field(..., min_length=2, max_length=100)
    author_email: str = ""
    version: str = Field(default="1.0.0")
    repository_url: str = ""
    documentation_url: str = ""
    config: dict = Field(default_factory=dict, description="Plugin configuration (YAML-compatible)")
    tags: list[str] = Field(default_factory=list)
    target_countries: list[str] = Field(default_factory=list, description="ISO country codes")
    target_rivers: list[str] = Field(default_factory=list)
    license: str = Field(default="Apache-2.0")
    ethics_compliant: bool = Field(default=False, description="Self-certified ethics compliance")


class PluginEntry(BaseModel):
    """Full plugin registry entry."""
    plugin_id: str
    name: str
    plugin_type: PluginType
    description: str
    author: str
    author_email: str
    version: str
    status: PluginStatus
    repository_url: str
    documentation_url: str
    config: dict
    tags: list[str]
    target_countries: list[str]
    target_rivers: list[str]
    license: str
    ethics_compliant: bool
    downloads: int
    stars: int
    submitted_at: str
    reviewed_at: str
    reviewer: str


# ── In-Memory Store ──────────────────────────────────────────────────────

_plugins: list[dict] = [
    # Pre-loaded community plugins
    {
        "plugin_id": "basin-kaveri-karnataka",
        "name": "Kaveri River Basin — Karnataka",
        "plugin_type": PluginType.BASIN_CONFIG.value,
        "description": "Complete ARGUS deployment config for Kaveri basin. KRS Dam to Mysore corridor, 78 villages, 12 gauge stations.",
        "author": "ARGUS Core Team",
        "author_email": "basins@argus.foundation",
        "version": "2.1.0",
        "status": PluginStatus.APPROVED.value,
        "repository_url": "https://github.com/argus-foundation/basin-kaveri",
        "documentation_url": "https://docs.argus.foundation/basins/kaveri",
        "config": {
            "basin": {"name": "Kaveri River Basin", "country": "India", "river_system": "Kaveri"},
            "stations": [
                {"id": "krs_dam", "type": "dam", "lat": 12.4214, "lon": 76.5647},
                {"id": "mysore_gauge", "type": "gauge", "lat": 12.2958, "lon": 76.6394},
            ],
            "models": {"oracle_v2": {"enabled": True, "quantized": True}},
            "alerts": {"channels": ["sms", "whatsapp", "siren"], "languages": ["kn", "en", "hi"]},
        },
        "tags": ["india", "kaveri", "dam", "southern-india"],
        "target_countries": ["IN"],
        "target_rivers": ["Kaveri"],
        "license": "Apache-2.0",
        "ethics_compliant": True,
        "downloads": 342,
        "stars": 45,
        "submitted_at": "2025-06-15T00:00:00Z",
        "reviewed_at": "2025-06-16T00:00:00Z",
        "reviewer": "ethics_board",
    },
    {
        "plugin_id": "basin-mekong-vietnam",
        "name": "Mekong Delta — Vietnam",
        "plugin_type": PluginType.BASIN_CONFIG.value,
        "description": "Compound flooding: river + tidal surge + salinity intrusion. Can Tho and My Thuan corridor.",
        "author": "ARGUS Core Team",
        "author_email": "basins@argus.foundation",
        "version": "1.5.0",
        "status": PluginStatus.APPROVED.value,
        "repository_url": "https://github.com/argus-foundation/basin-mekong",
        "documentation_url": "https://docs.argus.foundation/basins/mekong",
        "config": {
            "basin": {"name": "Mekong Delta", "country": "Vietnam", "river_system": "Mekong", "flood_type": "compound"},
            "stations": [
                {"id": "can_tho", "type": "gauge", "lat": 10.0452, "lon": 105.7469},
                {"id": "my_thuan", "type": "gauge", "lat": 10.3613, "lon": 105.9053},
            ],
            "models": {"compound_flood": {"features": ["water_level", "rainfall", "tidal_height", "salinity"]}},
            "alerts": {"channels": ["sms", "zalo", "loudspeaker"], "languages": ["vi", "en"]},
        },
        "tags": ["vietnam", "mekong", "compound-flooding", "tidal"],
        "target_countries": ["VN"],
        "target_rivers": ["Mekong"],
        "license": "Apache-2.0",
        "ethics_compliant": True,
        "downloads": 156,
        "stars": 28,
        "submitted_at": "2025-10-01T00:00:00Z",
        "reviewed_at": "2025-10-02T00:00:00Z",
        "reviewer": "ethics_board",
    },
    {
        "plugin_id": "model-tidal-surge",
        "name": "Tidal Surge Prediction Model",
        "plugin_type": PluginType.MODEL.value,
        "description": "Specialized tidal surge model for coastal and delta basins. Uses tidal harmonics + wind + pressure.",
        "author": "Dr. Nguyen Van Minh",
        "author_email": "minh@vnmha.gov.vn",
        "version": "1.0.0",
        "status": PluginStatus.APPROVED.value,
        "repository_url": "https://github.com/vnmha/argus-tidal-surge",
        "documentation_url": "",
        "config": {
            "model_type": "tidal_surge",
            "features": ["tidal_height", "wind_speed", "wind_direction", "atmospheric_pressure", "water_level"],
            "architecture": "lstm",
            "pretrained_weights": "tidal_surge_mekong_v1.pt",
        },
        "tags": ["tidal", "coastal", "lstm", "compound-flooding"],
        "target_countries": ["VN", "BD", "MM"],
        "target_rivers": ["Mekong", "Ganges", "Irrawaddy"],
        "license": "MIT",
        "ethics_compliant": True,
        "downloads": 89,
        "stars": 15,
        "submitted_at": "2025-11-01T00:00:00Z",
        "reviewed_at": "2025-11-03T00:00:00Z",
        "reviewer": "technical_review",
    },
    {
        "plugin_id": "alert-community-radio",
        "name": "Community Radio Alert Channel",
        "plugin_type": PluginType.ALERT_CHANNEL.value,
        "description": "Alert plugin for FM community radio stations. Auto-generates TTS alerts in local languages via CHORUS.",
        "author": "ARGUS Core Team",
        "author_email": "alerts@argus.foundation",
        "version": "1.2.0",
        "status": PluginStatus.APPROVED.value,
        "repository_url": "https://github.com/argus-foundation/alert-community-radio",
        "documentation_url": "https://docs.argus.foundation/plugins/community-radio",
        "config": {
            "channel_type": "community_radio",
            "tts_engine": "chorus_global",
            "supported_languages": ["hi", "as", "bn", "ne", "vi", "km"],
            "broadcast_protocol": "icecast2",
            "max_message_length_seconds": 60,
        },
        "tags": ["radio", "tts", "chorus", "offline"],
        "target_countries": ["IN", "BD", "NP", "VN", "KH"],
        "target_rivers": [],
        "license": "Apache-2.0",
        "ethics_compliant": True,
        "downloads": 67,
        "stars": 22,
        "submitted_at": "2025-09-15T00:00:00Z",
        "reviewed_at": "2025-09-16T00:00:00Z",
        "reviewer": "ethics_board",
    },
    {
        "plugin_id": "datasource-bwdb-api",
        "name": "BWDB Bangladesh Gauge Adapter",
        "plugin_type": PluginType.DATA_SOURCE.value,
        "description": "Data source adapter for Bangladesh Water Development Board (BWDB) real-time gauge network.",
        "author": "ARGUS Bangladesh Chapter",
        "author_email": "bd@argus.foundation",
        "version": "1.0.0",
        "status": PluginStatus.APPROVED.value,
        "repository_url": "https://github.com/argus-foundation/datasource-bwdb",
        "documentation_url": "",
        "config": {
            "source_type": "gauge_network",
            "api_endpoint": "https://bwdb.gov.bd/api/v1/gauges",
            "auth_type": "api_key",
            "poll_interval_seconds": 900,
            "stations_available": 48,
            "data_format": "json",
        },
        "tags": ["bangladesh", "bwdb", "gauge", "government"],
        "target_countries": ["BD"],
        "target_rivers": ["Brahmaputra", "Ganges", "Meghna"],
        "license": "Apache-2.0",
        "ethics_compliant": True,
        "downloads": 34,
        "stars": 12,
        "submitted_at": "2025-10-15T00:00:00Z",
        "reviewed_at": "2025-10-17T00:00:00Z",
        "reviewer": "technical_review",
    },
]


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "plugin_registry",
        "status": "healthy",
        "total_plugins": len(_plugins),
        "approved_plugins": sum(1 for p in _plugins if p["status"] == PluginStatus.APPROVED.value),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/registry/plugins")
async def list_plugins(
    plugin_type: Optional[PluginType] = None,
    country: Optional[str] = Query(None, description="ISO country code filter"),
    status: Optional[PluginStatus] = None,
    tag: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all plugins with optional filters."""
    plugins = _plugins

    if plugin_type:
        plugins = [p for p in plugins if p["plugin_type"] == plugin_type.value]
    if country:
        plugins = [p for p in plugins if country.upper() in p.get("target_countries", [])]
    if status:
        plugins = [p for p in plugins if p["status"] == status.value]
    if tag:
        plugins = [p for p in plugins if tag.lower() in [t.lower() for t in p.get("tags", [])]]

    total = len(plugins)
    plugins = plugins[offset:offset + limit]

    return {
        "plugins": [
            {
                "plugin_id": p["plugin_id"],
                "name": p["name"],
                "plugin_type": p["plugin_type"],
                "description": p["description"],
                "author": p["author"],
                "version": p["version"],
                "status": p["status"],
                "tags": p["tags"],
                "target_countries": p["target_countries"],
                "downloads": p["downloads"],
                "stars": p["stars"],
                "ethics_compliant": p["ethics_compliant"],
            }
            for p in plugins
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/registry/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    """Get full plugin details including configuration."""
    for plugin in _plugins:
        if plugin["plugin_id"] == plugin_id:
            plugin["downloads"] += 1
            return plugin

    raise HTTPException(404, f"Plugin not found: {plugin_id}")


@app.post("/api/v1/registry/plugins")
async def submit_plugin(submission: PluginSubmission):
    """Submit a new plugin to the registry."""
    # Check for duplicate
    for existing in _plugins:
        if existing["name"].lower() == submission.name.lower():
            raise HTTPException(
                409,
                f"Plugin with name '{submission.name}' already exists. "
                "Use a different name or update the existing plugin.",
            )

    plugin_id = f"{submission.plugin_type.value}-{uuid.uuid4().hex[:8]}"

    entry = {
        "plugin_id": plugin_id,
        "name": submission.name,
        "plugin_type": submission.plugin_type.value,
        "description": submission.description,
        "author": submission.author,
        "author_email": submission.author_email,
        "version": submission.version,
        "status": PluginStatus.SUBMITTED.value,
        "repository_url": submission.repository_url,
        "documentation_url": submission.documentation_url,
        "config": submission.config,
        "tags": submission.tags,
        "target_countries": submission.target_countries,
        "target_rivers": submission.target_rivers,
        "license": submission.license,
        "ethics_compliant": submission.ethics_compliant,
        "downloads": 0,
        "stars": 0,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_at": "",
        "reviewer": "",
    }

    _plugins.append(entry)

    logger.info(
        "plugin_submitted",
        plugin_id=plugin_id,
        name=submission.name,
        type=submission.plugin_type.value,
        author=submission.author,
    )

    return {
        "plugin_id": plugin_id,
        "status": "SUBMITTED",
        "message": (
            f"Plugin '{submission.name}' submitted for review. "
            f"{'Ethics compliance self-certified.' if submission.ethics_compliant else 'NOTE: Ethics compliance not declared — review may be slower.'} "
            "Expect review within 5 business days."
        ),
    }


@app.get("/api/v1/registry/plugins/search")
async def search_plugins(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search plugins by name, description, tags, or rivers."""
    query = q.lower()
    results = []

    for plugin in _plugins:
        score = 0
        # Name match (highest weight)
        if query in plugin["name"].lower():
            score += 10
        # Description match
        if query in plugin["description"].lower():
            score += 5
        # Tag match
        if any(query in tag.lower() for tag in plugin.get("tags", [])):
            score += 7
        # River match
        if any(query in river.lower() for river in plugin.get("target_rivers", [])):
            score += 8
        # Country match
        if any(query.upper() == c for c in plugin.get("target_countries", [])):
            score += 6

        if score > 0:
            results.append((score, plugin))

    # Sort by relevance score
    results.sort(key=lambda x: x[0], reverse=True)

    return {
        "query": q,
        "results": [
            {
                "plugin_id": p["plugin_id"],
                "name": p["name"],
                "plugin_type": p["plugin_type"],
                "description": p["description"],
                "author": p["author"],
                "relevance_score": s,
                "downloads": p["downloads"],
                "stars": p["stars"],
            }
            for s, p in results[:limit]
        ],
        "total": len(results),
    }


@app.get("/api/v1/registry/stats")
async def registry_stats():
    """Registry-wide statistics."""
    type_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}
    total_downloads = 0

    for plugin in _plugins:
        ptype = plugin["plugin_type"]
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
        total_downloads += plugin.get("downloads", 0)

        for country in plugin.get("target_countries", []):
            country_counts[country] = country_counts.get(country, 0) + 1

    return {
        "total_plugins": len(_plugins),
        "by_type": type_counts,
        "by_country": country_counts,
        "total_downloads": total_downloads,
        "approved": sum(1 for p in _plugins if p["status"] == PluginStatus.APPROVED.value),
        "pending_review": sum(1 for p in _plugins if p["status"] in [PluginStatus.SUBMITTED.value, PluginStatus.UNDER_REVIEW.value]),
        "top_plugins": sorted(
            [{"plugin_id": p["plugin_id"], "name": p["name"], "downloads": p["downloads"]}
             for p in _plugins],
            key=lambda x: x["downloads"],
            reverse=True,
        )[:5],
    }


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "platform.plugin_registry.registry:app",
        host="0.0.0.0",
        port=5176,
        reload=True,
    )
