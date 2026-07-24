"""Developer Portal API — SDK docs, playground, and basin registry (port 5175).

Serves the developer documentation site and provides backend APIs
for the interactive basin deployment playground.

Endpoints:
  GET  /api/v1/docs/quickstart       → Quick start guide content
  GET  /api/v1/docs/sdk-reference    → Full SDK API reference
  POST /api/v1/playground/validate   → Validate basin YAML config
  POST /api/v1/playground/deploy     → Deploy basin to playground sandbox
  GET  /api/v1/playground/status/{id} → Check deployment status
  GET  /api/v1/registry/basins       → List community basin configs
  POST /api/v1/registry/basins       → Submit new basin config
  GET  /health                       → Liveness check

Run: ``uvicorn platform.developer_portal.api:app --reload --port 5175``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="ARGUS Developer Portal API",
    description="SDK documentation, playground, and basin registry",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────

class BasinConfig(BaseModel):
    """Basin configuration for validation."""
    yaml_content: str = Field(..., description="Basin YAML configuration")


class DeployRequest(BaseModel):
    """Playground deployment request."""
    config: str = Field(..., description="Basin YAML configuration")
    sandbox_name: str = Field(default="", description="Optional sandbox name")


class BasinRegistryEntry(BaseModel):
    """Community basin configuration."""
    basin_id: str
    name: str
    country: str
    river_system: str
    contributor: str
    yaml_config: str
    description: str = ""
    validated: bool = False
    downloads: int = 0
    submitted_at: str = ""


class DeploymentStatus(BaseModel):
    """Playground deployment status."""
    deployment_id: str
    status: str
    basin_name: str
    services_ready: int
    services_total: int
    prediction_api_url: str = ""
    elapsed_seconds: float = 0
    logs: list[str] = Field(default_factory=list)


# ── In-Memory Store ──────────────────────────────────────────────────────

_deployments: dict[str, dict] = {}

_basin_registry: list[dict] = [
    {
        "basin_id": "kaveri-karnataka",
        "name": "Kaveri River Basin — Karnataka",
        "country": "India",
        "river_system": "Kaveri",
        "contributor": "ARGUS Core Team",
        "description": "KRS Dam to Mysore corridor. 78 villages, 12 gauge stations.",
        "validated": True,
        "downloads": 342,
        "submitted_at": "2025-06-15T00:00:00Z",
        "yaml_config": """basin:
  name: "Kaveri River Basin — Karnataka"
  country: India
  river_system: Kaveri
  region: Karnataka

stations:
  - id: krs_dam
    name: "KRS Dam"
    lat: 12.4214
    lon: 76.5647
    type: dam
    is_intervention_node: true
  - id: mysore_gauge
    name: "Mysore City Gauge"
    lat: 12.2958
    lon: 76.6394
    type: gauge

villages:
  count: 78
  population: 245000

models:
  xgboost:
    features: [water_level, rainfall, soil_moisture, upstream_flow]
  oracle_v2:
    enabled: true
    quantized: true

alerts:
  channels: [sms, whatsapp, siren]
  languages: [kn, en, hi]
""",
    },
    {
        "basin_id": "brahmaputra-bangladesh",
        "name": "Brahmaputra-Jamuna — Bangladesh",
        "country": "Bangladesh",
        "river_system": "Brahmaputra",
        "contributor": "ARGUS Core Team",
        "description": "Cross-border deployment with 48hr upstream signal from India.",
        "validated": True,
        "downloads": 218,
        "submitted_at": "2025-08-20T00:00:00Z",
        "yaml_config": """basin:
  name: "Brahmaputra-Jamuna — Bangladesh"
  country: Bangladesh
  river_system: Brahmaputra
  upstream_country: India
  upstream_signal_hours: 48

stations:
  - id: bahadurabad
    name: "Bahadurabad"
    lat: 25.18
    lon: 89.67
    type: gauge
    source: BWDB
  - id: teesta_barrage
    name: "Teesta Barrage"
    lat: 25.83
    lon: 89.55
    type: dam
    is_intervention_node: true

villages:
  count: 94
  population: 520000

models:
  xgboost:
    features: [water_level, rainfall, soil_moisture, upstream_flow, tidal]
  oracle_v2:
    enabled: true

alerts:
  channels: [sms, bkash, community_radio]
  languages: [bn, en]
""",
    },
    {
        "basin_id": "mekong-vietnam",
        "name": "Mekong Delta — Vietnam",
        "country": "Vietnam",
        "river_system": "Mekong",
        "contributor": "ARGUS Core Team",
        "description": "Compound flooding: river + tidal surge + salinity intrusion.",
        "validated": True,
        "downloads": 156,
        "submitted_at": "2025-10-01T00:00:00Z",
        "yaml_config": """basin:
  name: "Mekong Delta — Vietnam"
  country: Vietnam
  river_system: Mekong
  flood_type: compound

stations:
  - id: can_tho
    name: "Can Tho"
    lat: 10.0452
    lon: 105.7469
    type: gauge
    source: VNMHA
  - id: my_thuan
    name: "My Thuan Bridge"
    lat: 10.3613
    lon: 105.9053
    type: gauge

villages:
  count: 67
  population: 380000

models:
  compound_flood:
    features: [water_level, rainfall, tidal_height, salinity, wind_speed]
  oracle_v2:
    enabled: true

alerts:
  channels: [sms, zalo, loudspeaker]
  languages: [vi, en]
""",
    },
]


# ── Quick Start Content ──────────────────────────────────────────────────

QUICKSTART_CONTENT = {
    "title": "Deploy ARGUS for Your Basin in 30 Minutes",
    "steps": [
        {
            "step": 1,
            "title": "Install the ARGUS SDK",
            "command": "pip install argus-flood-sdk",
            "description": "The ARGUS SDK provides everything you need to configure, deploy, and monitor a flood early warning system.",
        },
        {
            "step": 2,
            "title": "Configure Your Basin",
            "command": "argus init my-basin --template=river",
            "description": "Creates a basin.yaml configuration file. Edit it to add your gauge stations, villages, and alert channels.",
            "example_yaml": """basin:
  name: "My River Basin"
  country: "Your Country"
  river_system: "Your River"

stations:
  - id: upstream_gauge
    name: "Upstream Gauge Station"
    lat: 0.0
    lon: 0.0
    type: gauge

villages:
  count: 50
  population: 100000

models:
  oracle_v2:
    enabled: true
    quantized: true

alerts:
  channels: [sms, whatsapp]
  languages: [en]
""",
        },
        {
            "step": 3,
            "title": "Deploy and Train",
            "command": "argus deploy my-basin/basin.yaml --train",
            "description": "Deploys all ARGUS microservices, trains models on your basin data, and starts real-time prediction.",
        },
    ],
    "next_steps": [
        "Add more gauge stations to improve accuracy",
        "Configure CHORUS for community voice reporting",
        "Set up evacuation routes in the dashboard",
        "Apply for an ARGUS Foundation grant if eligible",
    ],
}


SDK_REFERENCE = {
    "title": "ARGUS SDK Reference",
    "version": "3.0.0",
    "modules": [
        {
            "name": "argus.Basin",
            "description": "Basin configuration and management",
            "methods": [
                {"name": "Basin.from_config(path)", "description": "Load basin from YAML file", "returns": "Basin"},
                {"name": "Basin.from_registry(basin_id)", "description": "Load from community registry", "returns": "Basin"},
                {"name": "Basin.validate()", "description": "Validate configuration", "returns": "list[str]"},
                {"name": "Basin.to_yaml(path)", "description": "Export configuration", "returns": "None"},
            ],
        },
        {
            "name": "argus.ARGUSDeployment",
            "description": "Full deployment lifecycle management",
            "methods": [
                {"name": "ARGUSDeployment(basin)", "description": "Create deployment from basin config", "returns": "ARGUSDeployment"},
                {"name": "connect_data_sources()", "description": "Connect to gauges, weather APIs, satellite feeds", "returns": "dict"},
                {"name": "train_models()", "description": "Train XGBoost, PINN, ORACLE v2 models", "returns": "TrainingReport"},
                {"name": "start()", "description": "Start all 12 microservices", "returns": "dict"},
                {"name": "monitor()", "description": "Check service health and drift", "returns": "dict"},
            ],
        },
        {
            "name": "argus.PredictionClient",
            "description": "Query flood predictions",
            "methods": [
                {"name": "get_latest(village_id)", "description": "Get latest prediction for a village", "returns": "dict"},
                {"name": "get_history(village_id, hours)", "description": "Get prediction history", "returns": "list"},
                {"name": "get_risk_map(basin_id)", "description": "Get basin-wide risk map", "returns": "dict"},
            ],
        },
        {
            "name": "argus.CausalClient",
            "description": "Causal inference and interventions",
            "methods": [
                {"name": "intervention(type, value)", "description": "Compute intervention effect", "returns": "dict"},
                {"name": "counterfactual(scenario)", "description": "Run counterfactual analysis", "returns": "dict"},
                {"name": "get_dag()", "description": "Get causal DAG structure", "returns": "dict"},
            ],
        },
    ],
}


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "developer_portal",
        "status": "healthy",
        "registry_basins": len(_basin_registry),
        "active_deployments": len(_deployments),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/docs/quickstart")
async def quickstart():
    """Quick start guide content."""
    return QUICKSTART_CONTENT


@app.get("/api/v1/docs/sdk-reference")
async def sdk_reference():
    """Full SDK API reference."""
    return SDK_REFERENCE


@app.post("/api/v1/playground/validate")
async def validate_config(req: BasinConfig):
    """Validate a basin YAML configuration."""
    try:
        config = yaml.safe_load(req.yaml_content)
    except yaml.YAMLError as e:
        return {
            "valid": False,
            "errors": [f"YAML parse error: {e}"],
            "warnings": [],
        }

    errors = []
    warnings = []

    # Required fields
    if "basin" not in config:
        errors.append("Missing required 'basin' section")
    else:
        basin = config["basin"]
        if "name" not in basin:
            errors.append("Missing 'basin.name'")
        if "country" not in basin:
            errors.append("Missing 'basin.country'")
        if "river_system" not in basin:
            warnings.append("Missing 'basin.river_system' — recommended for registry")

    if "stations" not in config:
        errors.append("Missing required 'stations' section — need at least 1 gauge")
    elif len(config["stations"]) < 1:
        errors.append("Need at least 1 station defined")
    else:
        for i, station in enumerate(config["stations"]):
            if "id" not in station:
                errors.append(f"Station {i}: missing 'id'")
            if "lat" not in station or "lon" not in station:
                warnings.append(f"Station {i}: missing coordinates (lat/lon)")

    if "villages" not in config:
        warnings.append("Missing 'villages' section — add for population coverage stats")

    if "models" not in config:
        warnings.append("No models configured — ORACLE v2 will be used by default")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "config_summary": {
            "basin_name": config.get("basin", {}).get("name", "Unknown"),
            "n_stations": len(config.get("stations", [])),
            "n_villages": config.get("villages", {}).get("count", 0),
            "models": list(config.get("models", {}).keys()),
        },
    }


@app.post("/api/v1/playground/deploy")
async def deploy_to_playground(req: DeployRequest):
    """Deploy a basin configuration to the sandbox playground."""
    # Validate first
    try:
        config = yaml.safe_load(req.config)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")

    deployment_id = f"PLY-{uuid.uuid4().hex[:8].upper()}"
    basin_name = config.get("basin", {}).get("name", "Unknown Basin")

    _deployments[deployment_id] = {
        "deployment_id": deployment_id,
        "status": "PROVISIONING",
        "basin_name": basin_name,
        "config": config,
        "services_ready": 0,
        "services_total": 12,
        "prediction_api_url": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "logs": [
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Deployment {deployment_id} created",
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Provisioning sandbox environment...",
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Validating basin configuration: {basin_name}",
            f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Starting ORACLE v2 model training...",
        ],
    }

    # Simulate progressive deployment
    import asyncio

    async def simulate_deployment():
        services = [
            "ingestion", "feature_engine", "prediction", "causal_engine",
            "alert_dispatcher", "oracle_v2", "chorus", "evacuation_rl",
            "mirror", "flood_ledger", "model_monitor", "api_gateway",
        ]
        for i, svc in enumerate(services):
            await asyncio.sleep(0.5)
            if deployment_id in _deployments:
                _deployments[deployment_id]["services_ready"] = i + 1
                _deployments[deployment_id]["logs"].append(
                    f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
                    f"Service {svc} started ({i+1}/{len(services)})"
                )

        if deployment_id in _deployments:
            _deployments[deployment_id]["status"] = "RUNNING"
            _deployments[deployment_id]["prediction_api_url"] = (
                f"https://playground.argus.foundation/api/{deployment_id}/predict"
            )
            _deployments[deployment_id]["logs"].append(
                f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
                f"All services healthy. Prediction API ready."
            )

    asyncio.create_task(simulate_deployment())

    logger.info("playground_deployment_started", id=deployment_id, basin=basin_name)

    return {
        "deployment_id": deployment_id,
        "status": "PROVISIONING",
        "basin_name": basin_name,
        "estimated_time_seconds": 180,
        "message": f"Deploying {basin_name}. Check status at /api/v1/playground/status/{deployment_id}",
    }


@app.get("/api/v1/playground/status/{deployment_id}")
async def deployment_status(deployment_id: str):
    """Check playground deployment status."""
    if deployment_id not in _deployments:
        raise HTTPException(404, f"Deployment not found: {deployment_id}")

    dep = _deployments[deployment_id]
    return DeploymentStatus(
        deployment_id=dep["deployment_id"],
        status=dep["status"],
        basin_name=dep["basin_name"],
        services_ready=dep["services_ready"],
        services_total=dep["services_total"],
        prediction_api_url=dep.get("prediction_api_url", ""),
        logs=dep.get("logs", []),
    )


# ── Basin Registry ──────────────────────────────────────────────────────

@app.get("/api/v1/registry/basins")
async def list_basins(country: Optional[str] = None):
    """List all community-contributed basin configurations."""
    basins = _basin_registry

    if country:
        basins = [b for b in basins if b["country"].lower() == country.lower()]

    return {
        "basins": [
            {
                "basin_id": b["basin_id"],
                "name": b["name"],
                "country": b["country"],
                "river_system": b["river_system"],
                "contributor": b["contributor"],
                "description": b["description"],
                "validated": b["validated"],
                "downloads": b["downloads"],
                "submitted_at": b["submitted_at"],
            }
            for b in basins
        ],
        "total": len(basins),
    }


@app.get("/api/v1/registry/basins/{basin_id}")
async def get_basin(basin_id: str):
    """Get full basin configuration including YAML."""
    for basin in _basin_registry:
        if basin["basin_id"] == basin_id:
            basin["downloads"] += 1
            return basin

    raise HTTPException(404, f"Basin not found: {basin_id}")


@app.post("/api/v1/registry/basins")
async def submit_basin(entry: BasinRegistryEntry):
    """Submit a new basin configuration to the community registry."""
    # Validate YAML
    try:
        yaml.safe_load(entry.yaml_config)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML config: {e}")

    entry_dict = entry.model_dump()
    entry_dict["submitted_at"] = datetime.now(timezone.utc).isoformat()
    entry_dict["validated"] = False  # Requires manual review
    entry_dict["downloads"] = 0

    _basin_registry.append(entry_dict)

    logger.info(
        "basin_submitted",
        basin_id=entry.basin_id,
        country=entry.country,
        contributor=entry.contributor,
    )

    return {
        "basin_id": entry.basin_id,
        "status": "SUBMITTED",
        "message": "Basin configuration submitted for review. "
                   "Expect validation within 48 hours.",
    }


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "platform.developer_portal.api:app",
        host="0.0.0.0",
        port=5175,
        reload=True,
    )
