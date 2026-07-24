# ARGUS AI Ethics Framework v1.0

**Effective Date:** January 2025  
**Last Review:** June 2025  
**Next Review:** December 2025  
**Governing Body:** ARGUS Foundation Ethics Board  

---

## Preamble

ARGUS is an AI-powered flood early warning system designed to protect vulnerable communities across South and Southeast Asia. The system processes hydrological, satellite, social media, and community-reported data to issue flood warnings that directly affect human lives and livelihoods.

Given the life-critical nature of our technology, we hold ourselves to the highest ethical standards. This framework establishes binding principles for all ARGUS deployments, contributors, and partner organizations.

---

## Core Principles

### 1. Accuracy Above All Else

**Commitment:** ARGUS predictions must meet minimum accuracy thresholds before deployment to any basin.

- **Minimum F1-score:** 0.85 for flood/no-flood binary classification
- **Maximum false negative rate:** ≤5% — missing a real flood is unacceptable
- **Lead time requirement:** ≥6 hours for actionable warnings
- **Model drift monitoring:** Automated retraining triggers when F1 drops below 0.83
- **Ground truth validation:** Every deployment must have at least 1 verified gauge station

**Rationale:** Communities trust ARGUS with their lives. A missed flood warning (false negative) has catastrophic consequences — far worse than a false alarm. We calibrate our models to err on the side of caution.

**Implementation:**
- `model_monitor` service continuously tracks prediction accuracy metrics
- Automatic alert to Ethics Board when F1 drops below threshold
- Quarterly accuracy audits against IMD/CWC official observations
- ORACLE v2 maintains separate accuracy benchmarks (F1 ≥ 0.92)

---

### 2. Explainability & Transparency

**Commitment:** Every ARGUS prediction must be explainable to a non-technical stakeholder.

- **Feature attribution:** All predictions include top-3 causal factors
- **Causal DAG visibility:** The causal graph is always accessible via the API
- **Counterfactual reasoning:** "What if dam X released 20% less?" must be answerable
- **MIRROR system:** Provides natural-language explanations of why a warning was issued
- **Model cards:** Every deployed model has a published model card with training data, limitations, and bias assessments

**Rationale:** District Magistrates and community leaders need to understand *why* a warning was issued, not just that one was issued. Blind trust in opaque AI is dangerous.

**Implementation:**
- `causal_engine` provides SHAP-based feature importance for every prediction
- MIRROR generates human-readable narratives with confidence intervals
- ARGUS Copilot translates technical explanations into local context
- All model cards published at `/api/v1/model-cards/`

---

### 3. Equity & Anti-Bias

**Commitment:** ARGUS must not systematically under-serve any community based on geography, income, language, caste, religion, or political affiliation.

- **Alert equity audits:** Monthly review of alert distribution vs. actual flood events
- **Language parity:** CHORUS supports all major languages in each deployment basin (≥3 languages per basin)
- **Connectivity-aware design:** ORACLE v2 runs on ARM devices (500KB, 80ms) for areas with no internet
- **Community voice weighting:** CHORUS social reports from marginalized communities receive equal weight regardless of social media engagement
- **Coverage gap monitoring:** Automated flagging when any village >5km from nearest gauge has no satellite backup

**Rationale:** Flood vulnerability is highest among marginalized communities — precisely those most likely to be excluded by technology. Equity is not optional.

**Implementation:**
- Alert distribution reports generated monthly by `model_monitor`
- CHORUS `global_language_support.py` ensures linguistic coverage
- ORACLE v2 ARM quantization enables offline-first deployment
- ScarNet satellite coverage fills infrastructure gaps
- Foundation grant program prioritizes under-served basins (2× scoring weight)

---

### 4. Informed Consent & Data Privacy

**Commitment:** All personal and community data processed by ARGUS requires informed consent and follows data minimization principles.

- **CHORUS consent:** Voice reports are opt-in. Users are informed that their reports are processed by AI.
- **Location data:** Village-level aggregation only — no individual GPS tracking
- **Data retention:** Raw CHORUS audio deleted after classification (max 72-hour retention)
- **No facial recognition:** CCTV integration for water level gauging only — CV Gauging processes water line, not people
- **GDPR/DPDP compliance:** Right to erasure honored within 48 hours for any personal data
- **Cross-border data:** Data from upstream countries (India → Bangladesh signal) transmitted via Kafka with encryption, shared only with downstream government agencies per bilateral agreement

**Rationale:** Communities contributing data to ARGUS are exercising trust. That trust must be reciprocated with strict data protections.

**Implementation:**
- CHORUS `main.py` logs only classification results, not raw text/audio
- CV Gauging masked inference — no faces stored or processed
- Kafka TLS encryption for all inter-service and cross-border data
- Data retention policies enforced by automated cleanup jobs
- Annual privacy audits by external assessor

---

### 5. No Weaponization

**Commitment:** ARGUS technology must never be used for:

- **Military or intelligence purposes** — flood data must not be weaponized for strategic advantage
- **Forced displacement** — warnings must enable *voluntary* evacuation, never forced removal
- **Insurance discrimination** — ARGUS risk scores must not be used to deny insurance coverage to individuals
- **Political manipulation** — warning issuance must not be influenced by election cycles or political pressure
- **Commercial exploitation** — community data must not be sold to third parties

**Enforcement:**
- All deployments require signed Non-Weaponization Agreement (NWA)
- Grant recipients must agree to NWA terms
- SDK license includes anti-weaponization clause
- Ethics Board has authority to revoke deployment access for violations
- Annual compliance reviews for all active deployments

---

### 6. Human Authority

**Commitment:** ARGUS advises; humans decide. No automated action that directly affects human safety without human confirmation.

- **Warning issuance:** All RED and ORANGE alerts require human confirmation before public broadcast
- **Evacuation activation:** RL-optimized routes are *recommendations* — District Magistrate retains final authority
- **Dam operations:** Causal intervention suggestions for dam release are advisory only
- **Override logging:** All human overrides of ARGUS recommendations are logged and reviewed for model improvement
- **Graceful degradation:** If ARGUS systems fail, human-operated fallback procedures are documented

**Rationale:** AI systems can fail. Automated decisions in life-critical contexts are dangerous. The District Magistrate, not the algorithm, bears responsibility for public safety decisions.

**Implementation:**
- `alert_dispatcher` requires explicit `CONFIRM` action for high-severity alerts
- Copilot surfaces recommendations with confidence levels, not commands
- Override events logged to `flood_ledger` for immutable audit trail
- Bi-annual tabletop exercises with human operators (documented in `demo/rehearsal_log.md`)

---

### 7. Transparency in Failure

**Commitment:** When ARGUS fails — missed warnings, false alarms, system outages — we disclose publicly and learn.

- **Incident reports:** Published within 72 hours of any significant failure
- **Public post-mortems:** Root cause analysis shared with all stakeholders
- **False alarm accountability:** Every false alarm reviewed; pattern analysis to reduce recurrence
- **Missed event review:** Any flood event not warned ≥6 hours in advance triggers mandatory review
- **Accuracy degradation disclosure:** If model accuracy drops below threshold, affected communities are notified

**Rationale:** Trust in an early warning system requires honesty about its limitations. Hiding failures erodes trust and costs lives.

**Implementation:**
- Automated incident creation when prediction misses ground truth by >20%
- Post-mortem template in `docs/PRODUCTION_RUNBOOK.md`
- Monthly accuracy reports published to ARGUS Dashboard
- `model_monitor` drift detection triggers public notification workflow

---

## Ethics Review Process

### Pre-Deployment Review

Every new basin deployment undergoes Ethics Board review:

1. **Data Source Audit** — Verify all data sources have appropriate consent and legal basis
2. **Bias Assessment** — Check model performance across demographic segments
3. **Language Coverage** — Confirm CHORUS supports all major languages in the region
4. **Connectivity Assessment** — Verify offline capability for low-connectivity areas
5. **Stakeholder Mapping** — Identify all affected communities and their representatives
6. **Risk Assessment** — Document potential harms and mitigation strategies

### Ongoing Monitoring

- **Monthly:** Alert equity audits, false alarm rate review
- **Quarterly:** Model accuracy audit against official observations
- **Semi-annually:** Full ethics framework compliance review
- **Annually:** External ethics audit by independent assessor

### Escalation Process

| Severity | Trigger | Response Time | Authority |
|----------|---------|---------------|-----------|
| CRITICAL | Missed flood warning causing harm | 2 hours | Board Chair + CTO |
| HIGH | Systematic bias detected in alerts | 24 hours | Ethics Board |
| MEDIUM | Privacy breach or data misuse | 48 hours | Board + Legal |
| LOW | Community complaint about accuracy | 1 week | Technical team |

---

## Board Composition

The ARGUS Ethics Board comprises:

1. **Technical Lead** — ARGUS core team member (rotating annually)
2. **Community Representative** — From an active ARGUS deployment basin
3. **Disaster Management Expert** — From NDMA, BWDB, or equivalent
4. **AI Ethics Academic** — Independent researcher (rotating bi-annually)
5. **Legal/Privacy Expert** — Data protection specialist

**Quorum:** 3 of 5 members for routine decisions. 4 of 5 for deployment suspensions.

---

## Compliance & Enforcement

### License Requirements

The ARGUS SDK (Apache-2.0) includes an **Ethics Addendum** that requires:

- Agreement to the 7 core principles above
- Submission to Ethics Board jurisdiction for dispute resolution
- Annual self-certification of compliance
- Right of Ethics Board to revoke access for violations

### Reporting Violations

Anyone can report an ethics concern:

- **Email:** ethics@argus.foundation
- **Dashboard:** Ethics tab in ARGUS Dashboard (coming Phase 7)
- **Anonymous:** Via CHORUS voice reporting system in any supported language

---

## Amendments

This framework is a living document. Amendments require:

- Proposal from any Board member or community stakeholder
- 30-day public comment period
- 4/5 Board vote for approval
- Version-controlled in ARGUS repository

---

## Signatories

By contributing to ARGUS, all team members affirm these principles:

- **Accuracy** — We will never ship a model that doesn't meet thresholds
- **Explainability** — We will always make our reasoning transparent
- **Equity** — We will serve the most vulnerable first
- **Consent** — We will protect every person's data
- **Non-weaponization** — We will prevent misuse of our technology
- **Human authority** — We will keep humans in the loop
- **Transparency in failure** — We will be honest when we get it wrong

---

*"Technology without ethics is a weapon. Ethics without technology is wishful thinking. ARGUS is both."*
