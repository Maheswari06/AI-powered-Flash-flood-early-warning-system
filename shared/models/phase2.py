"""Phase 2 shared Pydantic models for ARGUS advanced AI layer.

Covers:
  - Causal Engine (GNN DAG, interventions, counterfactuals)
  - FloodLedger blockchain oracle (parametric insurance)
  - CHORUS community intelligence
  - Federated Learning
  - Evacuation RL
  - MIRROR counterfactual replay
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════
# Causal Engine — Node Types
# ══════════════════════════════════════════════════════════════════════════

class CausalNodeType(str, Enum):
    """Pearl-style node type classification."""
    OBSERVABLE = "OBSERVABLE"       # has a sensor or PINN virtual reading
    LATENT = "LATENT"              # inferred by model, no direct measurement
    INTERVENTION = "INTERVENTION"  # can be acted upon (dam gates, pumps)
    OUTCOME = "OUTCOME"            # what we care about (flood_depth, inundation_area)


# ══════════════════════════════════════════════════════════════════════════
# Causal Engine — Graph Primitives
# ══════════════════════════════════════════════════════════════════════════

class CausalNode(BaseModel):
    """A node in the causal DAG."""
    node_id: str
    variable: str            # e.g. "rainfall", "soil_moisture", "water_level"
    node_type: CausalNodeType = CausalNodeType.OBSERVABLE
    station_id: Optional[str] = None
    village_id: Optional[str] = None
    unit: Optional[str] = None           # "mm/hr", "m", "fraction", "m3/s"
    default_value: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    parents: List[str] = Field(default_factory=list)
    children: List[str] = Field(default_factory=list)
    structural_eq: Optional[str] = None   # human-readable structural equation


class CausalEdge(BaseModel):
    """Directed edge in the causal graph with strength."""
    source: str
    target: str
    weight: float = Field(ge=0.0, le=1.0)
    lag_hours: float = 0.0
    lag_minutes: int = 0
    mechanism: Optional[str] = None       # "hydrological", "meteorological", "anthropogenic"


class CausalDAG(BaseModel):
    """Complete causal directed acyclic graph."""
    dag_id: str = "beas_brahmaputra_v1"
    basin_id: str = "brahmaputra_upper"
    nodes: List[CausalNode] = Field(default_factory=list)
    edges: List[CausalEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    version: str = "2.0.0"


# ══════════════════════════════════════════════════════════════════════════
# Causal Engine — Intervention API Schemas
# ══════════════════════════════════════════════════════════════════════════

class InterventionSpec(BaseModel):
    """Specification for a single intervention action."""
    variable: str          # must be an INTERVENTION node in the DAG
    value: float
    unit: str = ""


class InterventionRequest(BaseModel):
    """do(X=x) intervention query — Pearl's do-calculus."""
    basin_id: str = "brahmaputra_upper"
    intervention: Optional[InterventionSpec] = None
    # Legacy flat fields (backward-compatible with existing code)
    variable: str = ""                    # variable to intervene on
    value: float = 0.0                    # fixed value
    target_variable: str = "downstream_flood_depth"
    target_variables: List[str] = Field(default_factory=list)
    village_id: Optional[str] = None
    context: Dict[str, float] = Field(default_factory=dict)
    current_observations: Optional[Dict[str, float]] = None
    n_monte_carlo: int = Field(default=100, ge=10, le=500)

    @property
    def effective_variable(self) -> str:
        return self.intervention.variable if self.intervention else self.variable

    @property
    def effective_value(self) -> float:
        return self.intervention.value if self.intervention else self.value


class InterventionResult(BaseModel):
    """Result of a causal intervention — both legacy and enhanced formats."""
    # Enhanced fields (Phase 2 Interventional Query API)
    baseline_depth_m: float = 0.0
    intervened_depth_m: float = 0.0
    damage_reduction_pct: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_lower_m: float = 0.0
    uncertainty_upper_m: float = 0.0
    causal_pathway: List[str] = Field(default_factory=list)
    recommendation: str = ""
    time_sensitive_minutes: int = 0
    time_sensitive_until: Optional[datetime] = None
    # Legacy fields (backward-compatible)
    intervention: Optional[InterventionRequest] = None
    original_values: Dict[str, float] = Field(default_factory=dict)
    counterfactual_values: Dict[str, float] = Field(default_factory=dict)
    causal_effects: Dict[str, float] = Field(default_factory=dict)   # ATE per target
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class CausalRiskResponse(BaseModel):
    """Current causal risk score with contributing paths."""
    basin_id: str
    causal_risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: str = "LOW"   # LOW, MODERATE, HIGH, CRITICAL
    top_contributing_nodes: List[Dict[str, Any]] = Field(default_factory=list)
    top_causal_paths: List[List[str]] = Field(default_factory=list)
    node_contributions: Dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class DAGStructureResponse(BaseModel):
    """DAG structure for dashboard visualization."""
    basin_id: str
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    intervention_nodes: List[str] = Field(default_factory=list)
    outcome_nodes: List[str] = Field(default_factory=list)


class InterventionOption(BaseModel):
    """Available intervention node and its valid range."""
    variable: str
    node_type: str = "INTERVENTION"
    unit: str = ""
    min_value: float = 0.0
    max_value: float = 1.0
    default_value: float = 0.0
    description: str = ""


class CounterfactualQuery(BaseModel):
    """What-if counterfactual query for MIRROR."""
    query_id: str
    scenario_name: str                    # e.g. "What if rainfall was 50% less?"
    base_event_id: Optional[str] = None   # historical event to replay
    modifications: Dict[str, float] = Field(default_factory=dict)
    village_id: Optional[str] = None


class CounterfactualResult(BaseModel):
    """Result of a counterfactual simulation."""
    query: CounterfactualQuery
    timeline: List[Dict[str, Any]] = Field(default_factory=list)  # time-stepped outcomes
    base_outcome: Dict[str, float] = Field(default_factory=dict)
    modified_outcome: Dict[str, float] = Field(default_factory=dict)
    risk_delta: float = 0.0              # change in peak risk
    lives_impact: Optional[int] = None   # estimated lives affected
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


# ══════════════════════════════════════════════════════════════════════════
# TFT Deep Track prediction
# ══════════════════════════════════════════════════════════════════════════

class TFTPrediction(BaseModel):
    """Temporal Fusion Transformer prediction output."""
    village_id: str
    horizon_hours: int = 24
    timesteps: List[str] = Field(default_factory=list)          # ISO timestamps
    point_forecast: List[float] = Field(default_factory=list)   # risk score per step
    lower_bound: List[float] = Field(default_factory=list)      # 10th percentile
    upper_bound: List[float] = Field(default_factory=list)      # 90th percentile
    attention_weights: Dict[str, float] = Field(default_factory=dict)  # feature importance
    created_at: datetime = Field(default_factory=lambda: datetime.now())


# ══════════════════════════════════════════════════════════════════════════
# CHORUS — Community Intelligence
# ══════════════════════════════════════════════════════════════════════════

class SentimentLevel(str, Enum):
    CALM = "CALM"
    CONCERNED = "CONCERNED"
    ANXIOUS = "ANXIOUS"
    PANIC = "PANIC"


class CommunityReport(BaseModel):
    """A single community intelligence report (WhatsApp / field)."""
    report_id: str
    village_id: str
    source: str = "whatsapp"              # whatsapp, field_worker, voice_call
    message: str = ""
    translated_text: Optional[str] = None # English translation
    language: str = "hi"                  # ISO 639-1
    sentiment: SentimentLevel = SentimentLevel.CALM
    keywords: List[str] = Field(default_factory=list)
    flood_mentioned: bool = False
    water_level_reported: Optional[float] = None  # meters, community-estimated
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    credibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class ChorusAggregation(BaseModel):
    """Aggregated community sentiment for a village."""
    village_id: str
    report_count: int = 0
    dominant_sentiment: SentimentLevel = SentimentLevel.CALM
    panic_ratio: float = 0.0             # fraction of PANIC reports
    avg_credibility: float = 0.5
    flood_mention_rate: float = 0.0
    community_risk_boost: float = 0.0    # additional risk signal [0, 0.3]
    top_keywords: List[str] = Field(default_factory=list)
    window_minutes: int = 60
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


# ══════════════════════════════════════════════════════════════════════════
# Federated Learning
# ══════════════════════════════════════════════════════════════════════════

class FederatedRound(BaseModel):
    """A single round of federated learning."""
    round_id: int
    global_model_version: str
    participating_nodes: List[str] = Field(default_factory=list)
    aggregation_method: str = "fedavg"   # fedavg, fedprox, scaffold
    global_loss: Optional[float] = None
    global_accuracy: Optional[float] = None
    privacy_budget_spent: float = 0.0    # ε for differential privacy
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class NodeUpdate(BaseModel):
    """Model update from a federated node."""
    node_id: str
    round_id: int
    num_samples: int = 0
    local_loss: float = 0.0
    local_accuracy: float = 0.0
    gradient_norm: float = 0.0
    clipped: bool = False                # was DP noise clipped?


# ══════════════════════════════════════════════════════════════════════════
# Evacuation RL
# ══════════════════════════════════════════════════════════════════════════

class EvacuationZone(BaseModel):
    """A zone in the evacuation graph."""
    zone_id: str
    village_id: str
    name: str
    population: int = 0
    lat: float = 0.0
    lon: float = 0.0
    elevation_m: float = 0.0
    is_safe_zone: bool = False
    capacity: Optional[int] = None       # safe zone capacity


class EvacuationRoute(BaseModel):
    """An edge in the evacuation graph."""
    route_id: str
    from_zone: str
    to_zone: str
    distance_km: float
    travel_time_min: float
    capacity_persons_hr: int = 500
    road_type: str = "paved"             # paved, unpaved, bridge, boat
    flood_risk: float = 0.0             # probability route is flooded
    is_passable: bool = True


class EvacuationAction(BaseModel):
    """RL agent's recommended evacuation action."""
    action_id: str
    village_id: str
    zone_id: str
    recommended_route: str               # route_id
    priority: int = 1                    # 1=highest
    estimated_travel_min: float = 0.0
    population_to_move: int = 0
    deadline_minutes: float = 60.0       # time window before flooding
    confidence: float = 0.5


class EvacuationPlan(BaseModel):
    """Complete evacuation plan for a village."""
    plan_id: str
    village_id: str
    trigger_level: str = "WARNING"       # alert level that triggered
    risk_score: float = 0.0
    actions: List[EvacuationAction] = Field(default_factory=list)
    total_population: int = 0
    estimated_clear_time_min: float = 0.0
    zones_at_risk: int = 0
    safe_zones_available: int = 0
    rl_reward: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


# ══════════════════════════════════════════════════════════════════════════
# FloodLedger — Blockchain Oracle (Parametric Insurance)
# ══════════════════════════════════════════════════════════════════════════

class FloodEvent(BaseModel):
    """A confirmed flood event recorded on-chain."""
    event_id: str
    basin_id: str = "brahmaputra_upper"
    flood_polygon_geojson: Optional[Dict[str, Any]] = None
    flood_polygon_hash: str = ""  # keccak256 of GeoJSON polygon
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now())
    satellite_confirmed: bool = False
    severity: str = "WARNING"    # WARNING, SEVERE, EXTREME
    tx_hash: Optional[str] = None  # blockchain transaction hash


class PayoutRecord(BaseModel):
    """Parametric insurance payout triggered by flood event."""
    event_id: str
    asset_id: str
    asset_name: str = ""
    amount_inr: float
    insurer_id: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.now())
    executed: bool = False
    tx_hash: Optional[str] = None


class IntersectedAsset(BaseModel):
    """An insured asset within a flood polygon."""
    asset_id: str
    name: str
    lat: float
    lon: float
    insured_value_inr: float
    insurer_id: str


class DemoTriggerRequest(BaseModel):
    """Request body for the demo-trigger endpoint."""
    basin_id: str = "brahmaputra_upper"
    severity: str = "SEVERE"
    satellite_confirmed: bool = True


class DemoTriggerResponse(BaseModel):
    """Response from demo-trigger with event + payouts."""
    event: FloodEvent
    intersected_assets: List[IntersectedAsset] = Field(default_factory=list)
    payouts: List[PayoutRecord] = Field(default_factory=list)
    total_payout_inr: float = 0.0


class LedgerEntry(BaseModel):
    """An immutable ledger entry for a flood event."""
    entry_id: str
    block_number: int
    village_id: str
    event_type: str = "prediction"       # prediction, alert, evacuation, verification
    payload: Dict[str, Any] = Field(default_factory=dict)
    data_hash: str = ""                  # SHA-256 of payload
    previous_hash: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    verified: bool = False
    verifier_node: Optional[str] = None


class LedgerChain(BaseModel):
    """Summary of the FloodLedger blockchain."""
    chain_id: str = "argus_flood_ledger_v1"
    length: int = 0
    last_hash: str = ""
    entries_24h: int = 0
    villages_tracked: int = 0
    integrity_verified: bool = True
