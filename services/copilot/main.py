"""ARGUS Copilot — LLM-powered natural language interface for DMs (port 8016).

District Magistrates are not data scientists.
They ask ARGUS questions in plain language and get actionable answers.

Examples:
  "How much time do I have before Majuli Ward 7 floods?"
  "Which road will close first and how long before the flood?"
  "If I open the Pandoh gate now, what happens downstream?"
  "How many buses do I need for full evacuation of Garamur?"

Architecture:
  Claude Opus 4.6 ↔ ARGUS Tool Calls ↔ Real ARGUS Microservices

Endpoints:
  POST /api/v1/copilot/chat        → Conversational interface
  POST /api/v1/copilot/quick       → Single-turn quick question
  GET  /api/v1/copilot/tools       → List available tools
  GET  /api/v1/copilot/history     → Conversation history
  POST /api/v1/copilot/demo        → Demo with canned responses
  GET  /health                     → Liveness check

Run: ``uvicorn services.copilot.main:app --reload --port 8016``
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# ── System Prompt ────────────────────────────────────────────────────────

ARGUS_SYSTEM_PROMPT = """
You are ARGUS Copilot — the AI assistant for District Magistrates
and NDRF officers managing flood emergencies.

You have real-time access to ARGUS data through function calls.
You speak with the authority of a senior hydrologist combined with
the urgency of an emergency responder.

Rules:
- Always lead with the most time-critical information
- Give specific numbers, not ranges when possible
- If confidence is below 70%, say so explicitly
- If a situation requires immediate action, say IMMEDIATE ACTION REQUIRED first
- Never hedge to the point of uselessness — officers need decisions, not uncertainty
- Speak simply. No jargon. A DM at 2AM reading this needs to act, not study.
- Always quote your data source (which ARGUS service provided the number)

When asked about interventions, call compute_causal_intervention first.
When asked about evacuation, call get_evacuation_plan first.
When asked about risk, call get_village_risk first.
When asked about roads, call get_road_closure_schedule first.
"""


# ── Tool Definitions ─────────────────────────────────────────────────────

COPILOT_TOOLS = [
    {
        "name": "get_village_risk",
        "description": (
            "Get current flood risk score, alert level, contributing factors, "
            "and time-to-flood estimate for a specific village or ward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "village_name": {
                    "type": "string",
                    "description": "Village name (e.g. 'Majuli Ward 7', 'Garamur', 'kullu_01')",
                },
                "basin_id": {
                    "type": "string",
                    "default": "brahmaputra_upper",
                    "description": "Basin identifier",
                },
            },
            "required": ["village_name"],
        },
    },
    {
        "name": "compute_causal_intervention",
        "description": (
            "Compute the effect of a specific intervention (dam gate opening, "
            "pump station activation, embankment breach) on downstream flood risk "
            "using the causal DAG engine. Returns damage reduction percentage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intervention_type": {
                    "type": "string",
                    "enum": ["dam_gate", "pump_station", "embankment_breach"],
                    "description": "Type of infrastructure intervention",
                },
                "intervention_value": {
                    "type": "number",
                    "description": "Intervention magnitude (e.g., gate opening % for dam_gate, m³/s for pump)",
                },
                "basin_id": {
                    "type": "string",
                    "default": "brahmaputra_upper",
                },
            },
            "required": ["intervention_type", "intervention_value"],
        },
    },
    {
        "name": "get_evacuation_plan",
        "description": (
            "Get current evacuation plan for a village or ward including "
            "routes, transport capacity, shelter locations, estimated "
            "evacuation time, and population counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "village_name": {
                    "type": "string",
                    "description": "Village or ward name",
                },
                "include_routes": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include detailed route information",
                },
            },
            "required": ["village_name"],
        },
    },
    {
        "name": "get_road_closure_schedule",
        "description": (
            "Get predicted road closure times for a district. "
            "Shows which roads will flood first and the estimated "
            "closure time for each route."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "district": {
                    "type": "string",
                    "description": "District name (e.g., 'Jorhat', 'Majuli')",
                },
                "hours_ahead": {
                    "type": "integer",
                    "default": 6,
                    "description": "How many hours ahead to predict",
                },
            },
            "required": ["district"],
        },
    },
    {
        "name": "send_emergency_alert",
        "description": (
            "Send an emergency alert to a village via all channels "
            "(SMS, WhatsApp, sirens, PA system). "
            "Requires District Magistrate authorization."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "village_name": {
                    "type": "string",
                    "description": "Target village or ward",
                },
                "alert_level": {
                    "type": "string",
                    "enum": ["ADVISORY", "WATCH", "WARNING", "EMERGENCY"],
                    "description": "Alert severity level",
                },
                "custom_message": {
                    "type": "string",
                    "description": "Optional custom message to include in alert",
                },
            },
            "required": ["village_name", "alert_level"],
        },
    },
]


# ── Demo Data ────────────────────────────────────────────────────────────

DEMO_RESPONSES = {
    "get_village_risk": {
        "village_name": "Majuli Ward 7",
        "risk_score": 0.91,
        "alert_level": "EMERGENCY",
        "confidence": 0.94,
        "time_to_flood_minutes": 78,
        "contributing_factors": [
            {"factor": "soil_saturation", "value": 91, "unit": "%", "weight": 0.35},
            {"factor": "upstream_level_change", "value": 340, "unit": "%", "weight": 0.30},
            {"factor": "rainfall_3h", "value": 45, "unit": "mm", "weight": 0.20},
            {"factor": "rate_of_rise", "value": 0.42, "unit": "m/hr", "weight": 0.15},
        ],
        "upstream_gauges": [
            {"name": "Nimatighat", "level_m": 87.2, "trend": "RISING", "rate": "+0.3m/hr"},
            {"name": "Jorhat", "level_m": 84.5, "trend": "RISING", "rate": "+0.4m/hr"},
        ],
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "model": "ORACLE_v2_MobileFloodFormer",
    },
    "compute_causal_intervention": {
        "intervention_type": "dam_gate",
        "current_risk": 0.91,
        "post_intervention_risk": 0.67,
        "risk_reduction_pct": 26.4,
        "downstream_impact": [
            {"village": "Majuli Ward 7", "risk_change": -0.24, "delay_minutes": 45},
            {"village": "Majuli Ward 3", "risk_change": -0.18, "delay_minutes": 60},
            {"village": "Neamatighat", "risk_change": -0.12, "delay_minutes": 30},
        ],
        "side_effects": [
            "Upstream reservoir level rises by 0.3m over 6 hours",
            "Downstream sediment load increases temporarily",
        ],
        "confidence": 0.87,
        "causal_model": "Brahmaputra_DAG_v3",
    },
    "get_evacuation_plan": {
        "village_name": "Majuli Ward 7",
        "population": 3420,
        "households": 684,
        "vulnerable_count": 245,
        "estimated_evacuation_time_minutes": 52,
        "transport": {
            "buses_required": 12,
            "buses_available": 8,
            "boats_required": 4,
            "boats_available": 6,
            "trips_needed": 3,
        },
        "routes": [
            {
                "route_id": "NH-715",
                "name": "NH-715 via Kamalabari",
                "distance_km": 12.5,
                "travel_time_min": 25,
                "status": "OPEN",
                "closes_in_minutes": 67,
                "capacity_vehicles_per_hour": 40,
            },
            {
                "route_id": "SH-41",
                "name": "SH-41 via Garamur",
                "distance_km": 18.3,
                "travel_time_min": 35,
                "status": "OPEN",
                "closes_in_minutes": 120,
                "capacity_vehicles_per_hour": 25,
            },
        ],
        "shelters": [
            {"name": "Kamalabari High School", "capacity": 500, "distance_km": 8.2, "current_occupancy": 45},
            {"name": "Majuli College", "capacity": 800, "distance_km": 14.1, "current_occupancy": 120},
        ],
        "margin_minutes": 15,
        "recommendation": "Evacuation feasible via NH-715. 15-minute margin. Start NOW.",
    },
    "get_road_closure_schedule": {
        "district": "Majuli",
        "prediction_horizon_hours": 6,
        "roads": [
            {
                "road_id": "NH-715",
                "name": "NH-715 (Kamalabari-Jorhat)",
                "current_status": "OPEN",
                "predicted_closure_time": "67 minutes",
                "flood_depth_at_closure": "0.3m",
                "reason": "Brahmaputra overflow at KM 14.5",
                "alternative": "SH-41 via Garamur (adds 20min)",
            },
            {
                "road_id": "SH-41",
                "name": "SH-41 (Garamur-Lakhimpur)",
                "current_status": "OPEN",
                "predicted_closure_time": "120 minutes",
                "flood_depth_at_closure": "0.2m",
                "reason": "Subansiri backwater effect",
                "alternative": "Boat via Nimatighat ferry",
            },
            {
                "road_id": "VR-7",
                "name": "Village Road 7 (Ward 7 internal)",
                "current_status": "WATERLOGGED",
                "predicted_closure_time": "Already partially flooded",
                "flood_depth_at_closure": "0.15m (current)",
                "reason": "Poor drainage + soil saturation",
                "alternative": "Foot evacuation to NH-715 junction",
            },
        ],
        "summary": "NH-715 closes first (67min). SH-41 remains open for 2 hours. "
                   "Start vehicle evacuation via NH-715 immediately.",
    },
    "send_emergency_alert": {
        "alert_id": "ALT-2026-0223-001",
        "village_name": "Majuli Ward 7",
        "alert_level": "EMERGENCY",
        "channels_dispatched": ["sms", "whatsapp", "siren", "pa_system"],
        "recipients": 3420,
        "delivered": 3180,
        "delivery_rate": 0.93,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "authorized_by": "DM-MAJULI",
    },
}


# ── Tool Execution ───────────────────────────────────────────────────────

GATEWAY_URL = os.getenv("ARGUS_GATEWAY_URL", "http://localhost:8000")

TOOL_ROUTES = {
    "get_village_risk": ("GET", "/api/v1/prediction/{village}"),
    "compute_causal_intervention": ("POST", "/api/v1/causal/intervene"),
    "get_evacuation_plan": ("GET", "/api/v1/evacuation/village/{village}"),
    "get_road_closure_schedule": ("GET", "/api/v1/evacuation/roads/{district}"),
    "send_emergency_alert": ("POST", "/api/v1/alert/dispatch"),
}


async def execute_tool(
    tool_name: str,
    inputs: dict,
    district: str,
    demo_mode: bool = True,
) -> dict:
    """
    Execute an ARGUS tool call.

    In demo mode: returns canned but realistic responses.
    In production: routes to real ARGUS microservices via API Gateway.
    """
    if demo_mode:
        result = DEMO_RESPONSES.get(tool_name, {"error": f"Unknown tool: {tool_name}"})
        # Merge any input-specific values
        if tool_name == "get_village_risk" and "village_name" in inputs:
            result = {**result, "village_name": inputs["village_name"]}
        if tool_name == "get_road_closure_schedule" and "district" in inputs:
            result = {**result, "district": inputs["district"]}
        if tool_name == "send_emergency_alert":
            result = {**result, **{k: v for k, v in inputs.items() if v}}

        logger.info("tool_executed_demo", tool=tool_name, inputs=inputs)
        return result

    # Production: route to real services
    route = TOOL_ROUTES.get(tool_name)
    if not route:
        return {"error": f"Unknown tool: {tool_name}"}

    method, path_template = route

    # Build URL
    url = GATEWAY_URL + path_template
    if "{village}" in url:
        village = inputs.get("village_name", "").lower().replace(" ", "_")
        url = url.replace("{village}", village)
    if "{district}" in url:
        url = url.replace("{district}", inputs.get("district", district))

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if method == "GET":
                r = await client.get(url, params=inputs)
            else:
                r = await client.post(url, json=inputs)
            return r.json()
    except Exception as e:
        logger.error("tool_execution_failed", tool=tool_name, error=str(e))
        return {"error": f"Service unavailable: {e}"}


# ── Copilot Engine ───────────────────────────────────────────────────────

async def run_copilot_turn(
    user_message: str,
    conversation_history: list,
    user_role: str,
    district: str,
    demo_mode: bool = True,
) -> tuple[str, list]:
    """
    Run one turn of the ARGUS Copilot conversation.

    In demo mode: generates responses without calling Claude API.
    In production: uses Claude Opus 4.6 with tool calling.

    Returns:
        (response_text, updated_history)
    """
    if demo_mode:
        return await _demo_copilot_turn(user_message, district)

    # Production mode with Claude API
    try:
        from anthropic import Anthropic
        client = Anthropic()
    except ImportError:
        logger.warning("anthropic_sdk_not_installed_falling_back_to_demo")
        return await _demo_copilot_turn(user_message, district)

    messages = conversation_history + [{"role": "user", "content": user_message}]

    system = (
        ARGUS_SYSTEM_PROMPT +
        f"\nCurrent district: {district}\nUser role: {user_role}\n"
        f"Current time: {datetime.now(timezone.utc).isoformat()}"
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        system=system,
        tools=COPILOT_TOOLS,
        messages=messages,
    )

    # Handle tool calls iteratively
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await execute_tool(
                    block.name, block.input, district, demo_mode=False
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            system=system,
            tools=COPILOT_TOOLS,
            messages=messages,
        )

    response_text = response.content[0].text
    messages.append({"role": "assistant", "content": response_text})

    return response_text, messages


async def _demo_copilot_turn(
    user_message: str,
    district: str,
) -> tuple[str, list]:
    """
    Demo mode: generates realistic responses using tool data
    without calling Claude API.
    """
    msg_lower = user_message.lower()

    # Route to appropriate demo responses
    if any(w in msg_lower for w in ["time", "flood", "risk", "ward", "majuli"]):
        data = await execute_tool("get_village_risk", {"village_name": "Majuli Ward 7"}, district)
        response = (
            f"**IMMEDIATE ACTION REQUIRED**\n\n"
            f"Risk: **{data['risk_score']:.0%}** — flood expected in **{data['time_to_flood_minutes']} minutes**.\n\n"
            f"Main causes:\n"
        )
        for factor in data["contributing_factors"]:
            response += f"- {factor['factor'].replace('_', ' ').title()}: {factor['value']}{factor['unit']}\n"
        response += (
            f"\nUpstream gauges are all RISING. "
            f"Nimatighat at {data['upstream_gauges'][0]['level_m']}m ({data['upstream_gauges'][0]['rate']}).\n\n"
            f"*Source: ORACLE v2 MobileFloodFormer, confidence {data['confidence']:.0%}*"
        )

    elif any(w in msg_lower for w in ["road", "close", "route", "highway"]):
        data = await execute_tool("get_road_closure_schedule", {"district": district}, district)
        response = f"**Road Closure Forecast — {data['district']} District**\n\n"
        for road in data["roads"]:
            status_icon = "🟢" if road["current_status"] == "OPEN" else "🔴"
            response += (
                f"{status_icon} **{road['name']}**: "
                f"{road['predicted_closure_time']} — {road['reason']}\n"
                f"   Alternative: {road['alternative']}\n\n"
            )
        response += f"**Summary**: {data['summary']}"

    elif any(w in msg_lower for w in ["evacuate", "evacuation", "bus", "shelter"]):
        data = await execute_tool("get_evacuation_plan", {"village_name": "Majuli Ward 7"}, district)
        response = (
            f"**Evacuation Plan — {data['village_name']}**\n\n"
            f"Population: {data['population']:,} ({data['households']} households)\n"
            f"Vulnerable: {data['vulnerable_count']}\n"
            f"Evacuation time: **{data['estimated_evacuation_time_minutes']} minutes**\n\n"
            f"**Transport:**\n"
            f"- Buses: {data['transport']['buses_available']}/{data['transport']['buses_required']} available\n"
            f"- Boats: {data['transport']['boats_available']}/{data['transport']['boats_required']} available\n"
            f"- Trips needed: {data['transport']['trips_needed']}\n\n"
            f"**Primary route:** {data['routes'][0]['name']} "
            f"({data['routes'][0]['distance_km']}km, {data['routes'][0]['travel_time_min']}min) — "
            f"**closes in {data['routes'][0]['closes_in_minutes']}min**\n\n"
            f"**Margin: {data['margin_minutes']} minutes.**\n\n"
            f"**{data['recommendation']}**"
        )

    elif any(w in msg_lower for w in ["dam", "gate", "open", "intervention", "pandoh"]):
        data = await execute_tool(
            "compute_causal_intervention",
            {"intervention_type": "dam_gate", "intervention_value": 25},
            district,
        )
        response = (
            f"**Causal Intervention Analysis — Dam Gate Opening**\n\n"
            f"Current risk: {data['current_risk']:.0%}\n"
            f"Post-intervention risk: **{data['post_intervention_risk']:.0%}** "
            f"(**-{data['risk_reduction_pct']:.1f}%**)\n\n"
            f"**Downstream Impact:**\n"
        )
        for village in data["downstream_impact"]:
            response += (
                f"- {village['village']}: risk {village['risk_change']:+.0%}, "
                f"delay +{village['delay_minutes']}min\n"
            )
        response += f"\n**Side effects:**\n"
        for effect in data["side_effects"]:
            response += f"- {effect}\n"
        response += f"\n*Confidence: {data['confidence']:.0%} — Model: {data['causal_model']}*"

    else:
        response = (
            f"I'm watching **{district}** district. Current status:\n\n"
            f"- 2 villages at **WATCH** level\n"
            f"- 1 village at **WARNING** level (Majuli Ward 7 — 91% risk)\n"
            f"- NH-715 predicted to flood in 67 minutes\n\n"
            f"What would you like to know? I can check:\n"
            f"- Flood risk for any village\n"
            f"- Road closure predictions\n"
            f"- Evacuation plans and transport\n"
            f"- Dam gate intervention impacts"
        )

    return response, []


# ── FastAPI App ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Chat request from the dashboard."""
    message: str = Field(..., min_length=1, max_length=2000)
    history: list = Field(default_factory=list)
    user_role: str = Field(default="DISTRICT_MAGISTRATE")
    district: str = Field(default="Majuli")
    demo_mode: bool = Field(default=True)


class ChatResponse(BaseModel):
    """Chat response."""
    response: str
    tools_used: list[str] = Field(default_factory=list)
    response_time_ms: float
    session_id: str
    timestamp: str


class QuickQuestionRequest(BaseModel):
    """Quick single-turn question."""
    question: str
    district: str = "Majuli"


# Session storage
_sessions: dict[str, list] = {}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info("copilot_starting", port=8016)
    yield
    logger.info("copilot_shutdown")


app = FastAPI(
    title="ARGUS Copilot",
    description="LLM-powered natural language interface for flood emergency management",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "service": "copilot",
        "status": "healthy",
        "active_sessions": len(_sessions),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/copilot/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Main conversational endpoint."""
    session_id = str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    response_text, updated_history = await run_copilot_turn(
        user_message=req.message,
        conversation_history=req.history,
        user_role=req.user_role,
        district=req.district,
        demo_mode=req.demo_mode,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Detect which tools were used
    tools_used = []
    msg_lower = req.message.lower()
    if any(w in msg_lower for w in ["risk", "flood", "time", "ward"]):
        tools_used.append("get_village_risk")
    if any(w in msg_lower for w in ["road", "close", "route"]):
        tools_used.append("get_road_closure_schedule")
    if any(w in msg_lower for w in ["evacuat", "bus", "shelter"]):
        tools_used.append("get_evacuation_plan")
    if any(w in msg_lower for w in ["dam", "gate", "intervention"]):
        tools_used.append("compute_causal_intervention")

    logger.info(
        "copilot_chat",
        session=session_id,
        message_len=len(req.message),
        tools=tools_used,
        response_ms=f"{elapsed_ms:.0f}",
    )

    return ChatResponse(
        response=response_text,
        tools_used=tools_used,
        response_time_ms=round(elapsed_ms, 1),
        session_id=session_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/api/v1/copilot/quick")
async def quick_question(req: QuickQuestionRequest):
    """Single-turn quick question — no conversation history."""
    response_text, _ = await run_copilot_turn(
        user_message=req.question,
        conversation_history=[],
        user_role="DISTRICT_MAGISTRATE",
        district=req.district,
        demo_mode=True,
    )
    return {"question": req.question, "response": response_text}


@app.get("/api/v1/copilot/tools")
async def list_tools():
    """List all available Copilot tools."""
    return {"tools": COPILOT_TOOLS, "count": len(COPILOT_TOOLS)}


@app.post("/api/v1/copilot/demo")
async def demo_conversation():
    """Run a full demo conversation with 3 canned questions."""
    demo_questions = [
        "How much time do I have before Majuli Ward 7 floods?",
        "Which road will close first?",
        "How many buses do I need for full evacuation?",
    ]

    results = []
    for question in demo_questions:
        response, _ = await run_copilot_turn(
            user_message=question,
            conversation_history=[],
            user_role="DISTRICT_MAGISTRATE",
            district="Majuli",
            demo_mode=True,
        )
        results.append({"question": question, "response": response})

    return {"demo_conversation": results, "questions_answered": len(results)}


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.copilot.main:app",
        host="0.0.0.0",
        port=8016,
        reload=True,
    )
