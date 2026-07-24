"""ARGUS Ethics Board — Automated Ethics Review System.

Provides pre-deployment and ongoing ethics compliance checks
for all ARGUS basin deployments.

Classes:
    EthicsReview   — Runs automated ethics checks against a basin deployment
    BiasAuditor    — Monthly alert equity audits
    ComplianceLog  — Immutable log of ethics decisions and escalations

Run checks:
    from foundation.ethics_board.ethics_review import EthicsReview
    review = EthicsReview(basin_id="brahmaputra-assam")
    report = await review.run_full_review()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ── Enums & Data Classes ────────────────────────────────────────────────

class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PrincipleID(str, Enum):
    ACCURACY = "P1_ACCURACY"
    EXPLAINABILITY = "P2_EXPLAINABILITY"
    EQUITY = "P3_EQUITY"
    CONSENT = "P4_CONSENT"
    NO_WEAPONIZATION = "P5_NO_WEAPONIZATION"
    HUMAN_AUTHORITY = "P6_HUMAN_AUTHORITY"
    TRANSPARENCY = "P7_TRANSPARENCY"


@dataclass
class Finding:
    """Individual finding from an ethics check."""
    principle: PrincipleID
    check_name: str
    passed: bool
    severity: Severity
    description: str
    recommendation: str = ""
    evidence: dict = field(default_factory=dict)


@dataclass
class EthicsReport:
    """Complete ethics review report for a basin."""
    review_id: str
    basin_id: str
    status: ReviewStatus
    findings: list[Finding]
    reviewed_at: str
    reviewer: str
    summary: str
    score: float  # 0-100

    @property
    def critical_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.CRITICAL and not f.passed]

    @property
    def pass_rate(self) -> float:
        if not self.findings:
            return 0.0
        return sum(1 for f in self.findings if f.passed) / len(self.findings)


# ── Ethics Review Engine ────────────────────────────────────────────────

class EthicsReview:
    """Automated ethics review for basin deployments.

    Checks all 7 ARGUS AI Ethics Framework principles with
    automated and semi-automated assessments.
    """

    def __init__(self, basin_id: str, deployment_config: dict | None = None):
        self.basin_id = basin_id
        self.config = deployment_config or {}
        self.review_id = f"ETH-{uuid.uuid4().hex[:8].upper()}"
        self.findings: list[Finding] = []

    async def run_full_review(self) -> EthicsReport:
        """Run all ethics checks and produce a report."""
        logger.info("ethics_review_started", review_id=self.review_id, basin=self.basin_id)

        # Run all principle checks
        await self._check_accuracy()
        await self._check_explainability()
        await self._check_equity()
        await self._check_consent()
        await self._check_no_weaponization()
        await self._check_human_authority()
        await self._check_transparency()

        # Compute overall score and status
        score = self._compute_score()
        status = self._determine_status(score)

        report = EthicsReport(
            review_id=self.review_id,
            basin_id=self.basin_id,
            status=status,
            findings=self.findings,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            reviewer="automated_system",
            summary=self._generate_summary(status, score),
            score=score,
        )

        logger.info(
            "ethics_review_completed",
            review_id=self.review_id,
            status=status.value,
            score=score,
            total_findings=len(self.findings),
            critical=len(report.critical_findings),
        )

        return report

    # ── Principle Checks ─────────────────────────────────────────────

    async def _check_accuracy(self):
        """P1: Accuracy Above All Else."""
        # Check minimum F1 threshold
        model_f1 = self.config.get("model_metrics", {}).get("f1_score", None)
        if model_f1 is not None:
            self.findings.append(Finding(
                principle=PrincipleID.ACCURACY,
                check_name="minimum_f1_score",
                passed=model_f1 >= 0.85,
                severity=Severity.CRITICAL,
                description=f"Model F1-score: {model_f1:.3f} (minimum: 0.850)",
                recommendation="Retrain model with additional data" if model_f1 < 0.85 else "",
                evidence={"f1_score": model_f1, "threshold": 0.85},
            ))
        else:
            self.findings.append(Finding(
                principle=PrincipleID.ACCURACY,
                check_name="minimum_f1_score",
                passed=False,
                severity=Severity.HIGH,
                description="No F1-score metric available — model not yet evaluated",
                recommendation="Run model evaluation before deployment",
            ))

        # Check false negative rate
        fnr = self.config.get("model_metrics", {}).get("false_negative_rate", None)
        if fnr is not None:
            self.findings.append(Finding(
                principle=PrincipleID.ACCURACY,
                check_name="false_negative_rate",
                passed=fnr <= 0.05,
                severity=Severity.CRITICAL,
                description=f"False negative rate: {fnr:.3f} (maximum: 0.050)",
                recommendation="Critical: FNR too high — missed floods unacceptable" if fnr > 0.05 else "",
                evidence={"fnr": fnr, "threshold": 0.05},
            ))

        # Check lead time
        lead_time = self.config.get("model_metrics", {}).get("avg_lead_time_hours", None)
        if lead_time is not None:
            self.findings.append(Finding(
                principle=PrincipleID.ACCURACY,
                check_name="minimum_lead_time",
                passed=lead_time >= 6.0,
                severity=Severity.HIGH,
                description=f"Average lead time: {lead_time:.1f}h (minimum: 6.0h)",
                recommendation="Insufficient lead time for evacuation" if lead_time < 6.0 else "",
                evidence={"lead_time_hours": lead_time, "threshold": 6.0},
            ))

        # Check gauge station coverage
        n_gauges = self.config.get("stations", {}).get("gauge_count", 0)
        self.findings.append(Finding(
            principle=PrincipleID.ACCURACY,
            check_name="gauge_station_coverage",
            passed=n_gauges >= 1,
            severity=Severity.CRITICAL,
            description=f"Verified gauge stations: {n_gauges} (minimum: 1)",
            recommendation="Need at least 1 verified gauge for ground truth" if n_gauges < 1 else "",
            evidence={"n_gauges": n_gauges},
        ))

    async def _check_explainability(self):
        """P2: Explainability & Transparency."""
        has_causal = self.config.get("services", {}).get("causal_engine", False)
        self.findings.append(Finding(
            principle=PrincipleID.EXPLAINABILITY,
            check_name="causal_engine_enabled",
            passed=has_causal,
            severity=Severity.HIGH,
            description=f"Causal engine enabled: {has_causal}",
            recommendation="Enable causal_engine for explainable predictions" if not has_causal else "",
        ))

        has_mirror = self.config.get("services", {}).get("mirror", False)
        self.findings.append(Finding(
            principle=PrincipleID.EXPLAINABILITY,
            check_name="mirror_narratives",
            passed=has_mirror,
            severity=Severity.MEDIUM,
            description=f"MIRROR narrative generation: {has_mirror}",
            recommendation="Enable MIRROR for human-readable explanations" if not has_mirror else "",
        ))

        has_model_cards = self.config.get("documentation", {}).get("model_cards", False)
        self.findings.append(Finding(
            principle=PrincipleID.EXPLAINABILITY,
            check_name="model_cards_published",
            passed=has_model_cards,
            severity=Severity.MEDIUM,
            description=f"Model cards published: {has_model_cards}",
            recommendation="Publish model cards with training data, limitations, biases" if not has_model_cards else "",
        ))

    async def _check_equity(self):
        """P3: Equity & Anti-Bias."""
        n_languages = self.config.get("languages", {}).get("count", 0)
        self.findings.append(Finding(
            principle=PrincipleID.EQUITY,
            check_name="language_coverage",
            passed=n_languages >= 3,
            severity=Severity.HIGH,
            description=f"Supported languages: {n_languages} (minimum: 3 per basin)",
            recommendation="Add more language support for equitable coverage" if n_languages < 3 else "",
            evidence={"n_languages": n_languages, "threshold": 3},
        ))

        has_offline = self.config.get("capabilities", {}).get("offline_mode", False)
        self.findings.append(Finding(
            principle=PrincipleID.EQUITY,
            check_name="offline_capability",
            passed=has_offline,
            severity=Severity.HIGH,
            description=f"Offline/ARM deployment capability: {has_offline}",
            recommendation="Enable ORACLE v2 quantized for offline deployment" if not has_offline else "",
        ))

        coverage_gap_km = self.config.get("coverage", {}).get("max_gap_km", 999)
        self.findings.append(Finding(
            principle=PrincipleID.EQUITY,
            check_name="coverage_gap",
            passed=coverage_gap_km <= 5.0,
            severity=Severity.MEDIUM,
            description=f"Max coverage gap: {coverage_gap_km:.1f}km (maximum: 5.0km)",
            recommendation="Add satellite backup (ScarNet) for uncovered villages" if coverage_gap_km > 5.0 else "",
            evidence={"max_gap_km": coverage_gap_km, "threshold": 5.0},
        ))

    async def _check_consent(self):
        """P4: Informed Consent & Data Privacy."""
        chorus_consent = self.config.get("chorus", {}).get("consent_enabled", False)
        self.findings.append(Finding(
            principle=PrincipleID.CONSENT,
            check_name="chorus_consent",
            passed=chorus_consent,
            severity=Severity.HIGH,
            description=f"CHORUS opt-in consent: {chorus_consent}",
            recommendation="Enable explicit consent for CHORUS voice reports" if not chorus_consent else "",
        ))

        data_retention_hours = self.config.get("data", {}).get("retention_hours", 999)
        self.findings.append(Finding(
            principle=PrincipleID.CONSENT,
            check_name="data_retention",
            passed=data_retention_hours <= 72,
            severity=Severity.MEDIUM,
            description=f"Raw data retention: {data_retention_hours}h (maximum: 72h)",
            recommendation="Reduce data retention to ≤72 hours" if data_retention_hours > 72 else "",
            evidence={"retention_hours": data_retention_hours, "threshold": 72},
        ))

        no_facial_recognition = self.config.get("cv_gauging", {}).get("face_detection_disabled", True)
        self.findings.append(Finding(
            principle=PrincipleID.CONSENT,
            check_name="no_facial_recognition",
            passed=no_facial_recognition,
            severity=Severity.CRITICAL,
            description=f"Facial recognition disabled: {no_facial_recognition}",
            recommendation="CRITICAL: Disable facial recognition immediately" if not no_facial_recognition else "",
        ))

    async def _check_no_weaponization(self):
        """P5: No Weaponization."""
        has_nwa = self.config.get("legal", {}).get("non_weaponization_agreement", False)
        self.findings.append(Finding(
            principle=PrincipleID.NO_WEAPONIZATION,
            check_name="nwa_signed",
            passed=has_nwa,
            severity=Severity.CRITICAL,
            description=f"Non-Weaponization Agreement signed: {has_nwa}",
            recommendation="Require NWA signature before deployment" if not has_nwa else "",
        ))

        users = self.config.get("users", {})
        military_users = users.get("military_access", False)
        self.findings.append(Finding(
            principle=PrincipleID.NO_WEAPONIZATION,
            check_name="no_military_access",
            passed=not military_users,
            severity=Severity.CRITICAL,
            description=f"Military/intelligence access: {military_users}",
            recommendation="CRITICAL: Remove military/intel access immediately" if military_users else "",
        ))

    async def _check_human_authority(self):
        """P6: Human Authority."""
        auto_broadcast = self.config.get("alerts", {}).get("auto_broadcast_enabled", False)
        self.findings.append(Finding(
            principle=PrincipleID.HUMAN_AUTHORITY,
            check_name="no_auto_broadcast",
            passed=not auto_broadcast,
            severity=Severity.CRITICAL,
            description=f"Auto-broadcast (no human confirmation): {auto_broadcast}",
            recommendation="CRITICAL: Disable auto-broadcast — human must confirm RED/ORANGE alerts" if auto_broadcast else "",
        ))

        override_logging = self.config.get("alerts", {}).get("override_logging", False)
        self.findings.append(Finding(
            principle=PrincipleID.HUMAN_AUTHORITY,
            check_name="override_logging",
            passed=override_logging,
            severity=Severity.HIGH,
            description=f"Human override logging enabled: {override_logging}",
            recommendation="Enable override logging for audit trail" if not override_logging else "",
        ))

    async def _check_transparency(self):
        """P7: Transparency in Failure."""
        incident_process = self.config.get("operations", {}).get("incident_response", False)
        self.findings.append(Finding(
            principle=PrincipleID.TRANSPARENCY,
            check_name="incident_response_process",
            passed=incident_process,
            severity=Severity.MEDIUM,
            description=f"Incident response process documented: {incident_process}",
            recommendation="Document incident response procedures" if not incident_process else "",
        ))

        drift_monitoring = self.config.get("services", {}).get("model_monitor", False)
        self.findings.append(Finding(
            principle=PrincipleID.TRANSPARENCY,
            check_name="drift_monitoring",
            passed=drift_monitoring,
            severity=Severity.HIGH,
            description=f"Model drift monitoring active: {drift_monitoring}",
            recommendation="Enable model_monitor for accuracy degradation alerts" if not drift_monitoring else "",
        ))

    # ── Scoring ──────────────────────────────────────────────────────

    SEVERITY_WEIGHT = {
        Severity.CRITICAL: 20,
        Severity.HIGH: 10,
        Severity.MEDIUM: 5,
        Severity.LOW: 2,
    }

    def _compute_score(self) -> float:
        """Compute ethics compliance score (0-100, higher = better)."""
        if not self.findings:
            return 0.0

        total_weight = sum(self.SEVERITY_WEIGHT[f.severity] for f in self.findings)
        earned = sum(
            self.SEVERITY_WEIGHT[f.severity]
            for f in self.findings
            if f.passed
        )

        return round(100.0 * earned / total_weight, 1) if total_weight > 0 else 0.0

    def _determine_status(self, score: float) -> ReviewStatus:
        """Determine review outcome based on score and critical findings."""
        critical_fails = [
            f for f in self.findings
            if f.severity == Severity.CRITICAL and not f.passed
        ]

        if critical_fails:
            return ReviewStatus.REJECTED

        if score >= 90:
            return ReviewStatus.APPROVED
        elif score >= 70:
            return ReviewStatus.CONDITIONAL
        else:
            return ReviewStatus.ESCALATED

    def _generate_summary(self, status: ReviewStatus, score: float) -> str:
        """Generate human-readable summary."""
        total = len(self.findings)
        passed = sum(1 for f in self.findings if f.passed)
        failed = total - passed

        summary_lines = [
            f"Ethics Review {self.review_id} for basin '{self.basin_id}'",
            f"Status: {status.value} (Score: {score}/100)",
            f"Checks: {passed}/{total} passed, {failed} failed",
        ]

        critical_fails = [
            f for f in self.findings
            if f.severity == Severity.CRITICAL and not f.passed
        ]
        if critical_fails:
            summary_lines.append(f"\nCRITICAL FAILURES ({len(critical_fails)}):")
            for cf in critical_fails:
                summary_lines.append(f"  - [{cf.check_name}] {cf.description}")
                if cf.recommendation:
                    summary_lines.append(f"    Recommendation: {cf.recommendation}")

        return "\n".join(summary_lines)


# ── Bias Auditor ────────────────────────────────────────────────────────

class BiasAuditor:
    """Monthly alert equity auditor.

    Analyzes alert distribution across demographics and geography
    to detect systematic bias in ARGUS warnings.
    """

    def __init__(self, basin_id: str):
        self.basin_id = basin_id

    async def run_equity_audit(
        self,
        alerts: list[dict],
        flood_events: list[dict],
    ) -> dict:
        """Compare alert distribution against actual flood events.

        Args:
            alerts: List of alerts with village_id, severity, timestamp
            flood_events: List of verified flood events with village_id, timestamp

        Returns:
            Audit report with equity metrics
        """
        if not alerts or not flood_events:
            return {
                "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
                "basin_id": self.basin_id,
                "status": "INSUFFICIENT_DATA",
                "message": "Need both alerts and flood events for equity audit",
            }

        # Count alerts per village
        alert_counts: dict[str, int] = {}
        for alert in alerts:
            vid = alert.get("village_id", "unknown")
            alert_counts[vid] = alert_counts.get(vid, 0) + 1

        # Count flood events per village
        event_counts: dict[str, int] = {}
        for event in flood_events:
            vid = event.get("village_id", "unknown")
            event_counts[vid] = event_counts.get(vid, 0) + 1

        # Identify under-served villages (floods > alerts)
        under_served = []
        for vid, flood_count in event_counts.items():
            alert_count = alert_counts.get(vid, 0)
            if alert_count < flood_count:
                under_served.append({
                    "village_id": vid,
                    "flood_events": flood_count,
                    "alerts_issued": alert_count,
                    "gap": flood_count - alert_count,
                })

        # Compute equity score
        total_events = sum(event_counts.values())
        total_covered = sum(
            min(alert_counts.get(vid, 0), count)
            for vid, count in event_counts.items()
        )
        equity_score = (total_covered / total_events * 100) if total_events > 0 else 0

        return {
            "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
            "basin_id": self.basin_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "equity_score": round(equity_score, 1),
            "total_flood_events": total_events,
            "total_alerts": sum(alert_counts.values()),
            "villages_under_served": under_served,
            "villages_total": len(event_counts),
            "status": "PASS" if equity_score >= 95 else "REVIEW_NEEDED",
        }


# ── Compliance Log ──────────────────────────────────────────────────────

class ComplianceLog:
    """Immutable log of ethics decisions, reviews, and escalations."""

    def __init__(self):
        self._entries: list[dict] = []

    def log_review(self, report: EthicsReport) -> str:
        """Log a completed ethics review."""
        entry = {
            "entry_id": f"CL-{uuid.uuid4().hex[:8].upper()}",
            "type": "ETHICS_REVIEW",
            "review_id": report.review_id,
            "basin_id": report.basin_id,
            "status": report.status.value,
            "score": report.score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "critical_findings": len(report.critical_findings),
        }
        self._entries.append(entry)
        logger.info("compliance_entry_logged", **entry)
        return entry["entry_id"]

    def log_escalation(
        self,
        basin_id: str,
        severity: Severity,
        description: str,
        assigned_to: str,
    ) -> str:
        """Log an escalation to the Ethics Board."""
        entry = {
            "entry_id": f"CL-{uuid.uuid4().hex[:8].upper()}",
            "type": "ESCALATION",
            "basin_id": basin_id,
            "severity": severity.value,
            "description": description,
            "assigned_to": assigned_to,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }
        self._entries.append(entry)
        logger.info("escalation_logged", **entry)
        return entry["entry_id"]

    def log_override(
        self,
        basin_id: str,
        alert_id: str,
        override_by: str,
        reason: str,
    ) -> str:
        """Log a human override of ARGUS recommendation."""
        entry = {
            "entry_id": f"CL-{uuid.uuid4().hex[:8].upper()}",
            "type": "HUMAN_OVERRIDE",
            "basin_id": basin_id,
            "alert_id": alert_id,
            "override_by": override_by,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._entries.append(entry)
        logger.info("human_override_logged", **entry)
        return entry["entry_id"]

    def get_entries(
        self,
        basin_id: str | None = None,
        entry_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve compliance log entries with optional filters."""
        entries = self._entries

        if basin_id:
            entries = [e for e in entries if e.get("basin_id") == basin_id]
        if entry_type:
            entries = [e for e in entries if e.get("type") == entry_type]

        return entries[-limit:]
