"""ARGUS Foundation Grant Program — Application & Scoring System (port 8019).

Provides up to $50,000 per basin deployment for NGOs and governments
that cannot afford commercial rates.

Funded by: FloodLedger API revenue share (5% of all payout fees)

Eligible applicants:
  - Government disaster management agencies in LMICs
  - NGOs operating in flood-prone regions
  - Academic institutions conducting flood research
  - Community organizations in at-risk areas

Endpoints:
  POST /api/v1/grants/apply           → Submit application
  GET  /api/v1/grants/{id}            → Get application status
  GET  /api/v1/grants/list             → List all applications (admin)
  GET  /api/v1/grants/criteria         → Get scoring criteria
  GET  /api/v1/grants/stats            → Grant program statistics
  POST /api/v1/grants/{id}/review      → Submit technical review (admin)
  GET  /health                         → Liveness check

Run: ``uvicorn foundation.grant_program.application_system:app --reload --port 8019``
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="ARGUS Foundation Grant Portal",
    description="Grant application system for ARGUS basin deployments in LMICs",
    version="1.0.0",
)


# ── Enums ────────────────────────────────────────────────────────────────

class ApplicationStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    TECHNICAL_REVIEW = "TECHNICAL_REVIEW"
    APPROVED = "APPROVED"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class OrganizationType(str, Enum):
    GOVERNMENT = "GOVERNMENT"
    NGO = "NGO"
    ACADEMIC = "ACADEMIC"
    COMMUNITY = "COMMUNITY"
    MULTILATERAL = "MULTILATERAL"


# ── Grant Criteria ───────────────────────────────────────────────────────

GRANT_CRITERIA = {
    "max_grant_usd": 50_000,
    "min_population": 10_000,
    "priority_countries": [
        "Bangladesh", "Nepal", "Vietnam", "Mozambique", "Pakistan",
        "Myanmar", "Cambodia", "Ethiopia", "Uganda", "Bolivia",
        "India", "Sri Lanka", "Philippines", "Indonesia", "Laos",
    ],
    "required_commitments": [
        "Deploy ARGUS for minimum 2 monsoon seasons",
        "Share anonymised event data with ARGUS Foundation",
        "Train at least 2 local technical staff",
        "Publish outcomes in ARGUS community forum",
    ],
    "scoring_weights": {
        "priority_country": 30,
        "population_at_risk": 25,
        "government_endorsement": 20,
        "no_existing_system": 15,
        "budget_reasonableness": 10,
    },
    "max_score": 100,
    "auto_approve_threshold": 85,
    "auto_reject_threshold": 25,
}


# ── Request / Response Schemas ───────────────────────────────────────────

class GrantApplication(BaseModel):
    """Grant application submission."""
    organization_name: str = Field(..., min_length=3, max_length=200)
    organization_type: OrganizationType
    country: str
    basin_name: str
    river_system: str = ""
    population_at_risk: int = Field(..., ge=1000)
    current_warning_system: str = Field(
        ..., description="'none', 'siren_only', 'basic_gauge', 'ffgs', 'other'"
    )
    requested_amount_usd: float = Field(..., gt=0, le=50_000)
    use_of_funds: str = Field(..., min_length=50, max_length=2000)
    deployment_plan: str = Field(
        default="", max_length=2000,
        description="Technical plan for ARGUS deployment"
    )
    technical_contact_email: str = Field(...)
    technical_contact_name: str = ""
    government_endorsement: bool = False
    endorsement_letter_url: str = ""
    previous_flood_losses_usd: float = 0
    n_flood_events_last_5yr: int = 0
    has_local_technical_staff: bool = False
    partner_ngos: list[str] = Field(default_factory=list)


class ApplicationResponse(BaseModel):
    """Response after application submission."""
    application_id: str
    status: ApplicationStatus
    initial_score: float
    score_breakdown: dict
    next_step: str
    estimated_decision: str
    submitted_at: str


class ReviewRequest(BaseModel):
    """Technical review submission."""
    reviewer_name: str
    technical_feasibility: float = Field(..., ge=0, le=10)
    community_impact: float = Field(..., ge=0, le=10)
    sustainability: float = Field(..., ge=0, le=10)
    comments: str = ""
    recommendation: str = Field(
        ..., pattern="^(approve|reject|revise)$"
    )


class GrantStats(BaseModel):
    """Grant program statistics."""
    total_applications: int
    approved: int
    under_review: int
    rejected: int
    total_disbursed_usd: float
    countries_served: list[str]
    basins_deploying: int
    population_covered: int


# ── In-Memory Store ──────────────────────────────────────────────────────

_applications: dict[str, dict] = {}
_reviews: dict[str, list[dict]] = {}


# ── Scoring Engine ───────────────────────────────────────────────────────

def _score_application(app: GrantApplication) -> tuple[float, dict]:
    """
    Score a grant application on a 0-100 scale.

    Scoring methodology:
      - Priority country:        0-30 points
      - Population at risk:      0-25 points
      - Government endorsement:  0-20 points
      - No existing system:      0-15 points
      - Budget reasonableness:   0-10 points

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {}

    # Priority country (30 pts)
    if app.country in GRANT_CRITERIA["priority_countries"]:
        breakdown["priority_country"] = 30
    elif app.country in ["Thailand", "Kenya", "Tanzania", "Peru", "Colombia"]:
        breakdown["priority_country"] = 15
    else:
        breakdown["priority_country"] = 5

    # Population at risk (25 pts)
    pop = app.population_at_risk
    if pop > 500_000:
        breakdown["population_at_risk"] = 25
    elif pop > 100_000:
        breakdown["population_at_risk"] = 20
    elif pop > 50_000:
        breakdown["population_at_risk"] = 15
    elif pop > 10_000:
        breakdown["population_at_risk"] = 10
    else:
        breakdown["population_at_risk"] = 5

    # Government endorsement (20 pts)
    if app.government_endorsement:
        breakdown["government_endorsement"] = 20
    elif app.organization_type == OrganizationType.GOVERNMENT:
        breakdown["government_endorsement"] = 15
    else:
        breakdown["government_endorsement"] = 0

    # No existing warning system (15 pts)
    system_scores = {
        "none": 15,
        "siren_only": 12,
        "basic_gauge": 8,
        "ffgs": 3,
        "other": 5,
    }
    breakdown["no_existing_system"] = system_scores.get(
        app.current_warning_system.lower(), 5
    )

    # Budget reasonableness (10 pts)
    cost_per_person = app.requested_amount_usd / max(app.population_at_risk, 1)
    if cost_per_person < 0.10:
        breakdown["budget_reasonableness"] = 10
    elif cost_per_person < 0.50:
        breakdown["budget_reasonableness"] = 7
    elif cost_per_person < 1.00:
        breakdown["budget_reasonableness"] = 4
    else:
        breakdown["budget_reasonableness"] = 2

    # Bonus points
    bonus = 0
    if app.n_flood_events_last_5yr > 10:
        bonus += 5
        breakdown["flood_history_bonus"] = 5
    if app.has_local_technical_staff:
        bonus += 3
        breakdown["local_staff_bonus"] = 3
    if len(app.partner_ngos) >= 2:
        bonus += 2
        breakdown["partnership_bonus"] = 2

    total = sum(breakdown.values())
    total = min(total, 100)  # Cap at 100
    breakdown["total"] = total

    return total, breakdown


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "grant_program",
        "status": "healthy",
        "applications": len(_applications),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/grants/apply", response_model=ApplicationResponse)
async def submit_application(application: GrantApplication):
    """Submit a new grant application."""
    # Validate budget
    if application.requested_amount_usd > GRANT_CRITERIA["max_grant_usd"]:
        raise HTTPException(
            400,
            f"Maximum grant amount is ${GRANT_CRITERIA['max_grant_usd']:,}",
        )

    if application.population_at_risk < GRANT_CRITERIA["min_population"]:
        raise HTTPException(
            400,
            f"Minimum population at risk is {GRANT_CRITERIA['min_population']:,}",
        )

    # Score application
    score, breakdown = _score_application(application)

    # Determine initial status
    if score >= GRANT_CRITERIA["auto_approve_threshold"]:
        status = ApplicationStatus.TECHNICAL_REVIEW
        next_step = "Fast-tracked to technical review (high score)"
        estimated = "14 days from submission"
    elif score <= GRANT_CRITERIA["auto_reject_threshold"]:
        status = ApplicationStatus.REJECTED
        next_step = "Application did not meet minimum criteria"
        estimated = "Decision made"
    else:
        status = ApplicationStatus.SUBMITTED
        next_step = "Initial review by grants committee within 14 days"
        estimated = "30 days from submission"

    app_id = f"GRANT-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    _applications[app_id] = {
        "id": app_id,
        "application": application.model_dump(),
        "score": score,
        "breakdown": breakdown,
        "status": status.value,
        "submitted_at": now,
        "updated_at": now,
        "reviews": [],
    }

    logger.info(
        "grant_application_submitted",
        app_id=app_id,
        org=application.organization_name,
        country=application.country,
        score=score,
        status=status.value,
    )

    return ApplicationResponse(
        application_id=app_id,
        status=status,
        initial_score=score,
        score_breakdown=breakdown,
        next_step=next_step,
        estimated_decision=estimated,
        submitted_at=now,
    )


@app.get("/api/v1/grants/{app_id}")
async def get_application(app_id: str):
    """Get application status and details."""
    if app_id not in _applications:
        raise HTTPException(404, f"Application not found: {app_id}")
    return _applications[app_id]


@app.get("/api/v1/grants/list")
async def list_applications(
    status: Optional[ApplicationStatus] = None,
    country: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List all applications (admin endpoint)."""
    apps = list(_applications.values())

    if status:
        apps = [a for a in apps if a["status"] == status.value]
    if country:
        apps = [a for a in apps
                if a["application"]["country"].lower() == country.lower()]

    apps.sort(key=lambda a: a["score"], reverse=True)
    return {"applications": apps[:limit], "total": len(apps)}


@app.get("/api/v1/grants/criteria")
async def get_criteria():
    """Return grant eligibility criteria and scoring methodology."""
    return GRANT_CRITERIA


@app.get("/api/v1/grants/stats", response_model=GrantStats)
async def get_stats():
    """Return grant program statistics."""
    apps = list(_applications.values())
    countries = set()
    total_pop = 0

    approved_count = 0
    total_disbursed = 0.0

    for app_data in apps:
        app_detail = app_data["application"]
        countries.add(app_detail["country"])
        total_pop += app_detail["population_at_risk"]
        if app_data["status"] == ApplicationStatus.APPROVED.value:
            approved_count += 1
            total_disbursed += app_detail["requested_amount_usd"]

    return GrantStats(
        total_applications=len(apps),
        approved=approved_count,
        under_review=sum(
            1 for a in apps
            if a["status"] in [
                ApplicationStatus.SUBMITTED.value,
                ApplicationStatus.UNDER_REVIEW.value,
                ApplicationStatus.TECHNICAL_REVIEW.value,
            ]
        ),
        rejected=sum(
            1 for a in apps
            if a["status"] == ApplicationStatus.REJECTED.value
        ),
        total_disbursed_usd=total_disbursed,
        countries_served=sorted(countries),
        basins_deploying=approved_count,
        population_covered=total_pop,
    )


@app.post("/api/v1/grants/{app_id}/review")
async def submit_review(app_id: str, review: ReviewRequest):
    """Submit a technical review for an application."""
    if app_id not in _applications:
        raise HTTPException(404, f"Application not found: {app_id}")

    review_data = {
        "reviewer": review.reviewer_name,
        "feasibility": review.technical_feasibility,
        "impact": review.community_impact,
        "sustainability": review.sustainability,
        "recommendation": review.recommendation,
        "comments": review.comments,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }

    _applications[app_id]["reviews"].append(review_data)

    # Auto-update status based on review
    if review.recommendation == "approve":
        _applications[app_id]["status"] = ApplicationStatus.APPROVED.value
    elif review.recommendation == "reject":
        _applications[app_id]["status"] = ApplicationStatus.REJECTED.value
    else:
        _applications[app_id]["status"] = ApplicationStatus.UNDER_REVIEW.value

    _applications[app_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(
        "grant_review_submitted",
        app_id=app_id,
        reviewer=review.reviewer_name,
        recommendation=review.recommendation,
    )

    return {
        "app_id": app_id,
        "new_status": _applications[app_id]["status"],
        "review": review_data,
    }


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "foundation.grant_program.application_system:app",
        host="0.0.0.0",
        port=8019,
        reload=True,
    )
