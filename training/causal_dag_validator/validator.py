"""
ARGUS — Causal DAG Expert Validation Workflow

Validates and refines the Brahmaputra causal DAG using:
  1. PC Algorithm (constraint-based causal discovery)
  2. Expert hydrologist review scoring
  3. Bootstrap stability analysis
  4. Edge-level confidence metrics

The validated DAG is used by the Causal Engine (Phase 2) to provide
physicist-guided flood predictions with explainable causal chains.
"""

from __future__ import annotations

import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict

import numpy as np

logger = logging.getLogger("argus.causal_validator")

# ═══════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CausalEdge:
    """A directed causal edge in the DAG."""
    source: str
    target: str
    lag_hours: int = 0
    mechanism: str = ""  # Physical mechanism description
    data_confidence: float = 0.0  # From PC algorithm (0-1)
    expert_confidence: float = 0.0  # From hydrologist review (0-1)
    bootstrap_stability: float = 0.0  # Fraction of bootstrap samples
    combined_score: float = 0.0

    def compute_combined_score(self, weights: dict = None):
        """Compute weighted combined confidence score."""
        w = weights or {"data": 0.4, "expert": 0.4, "bootstrap": 0.2}
        self.combined_score = (
            w["data"] * self.data_confidence +
            w["expert"] * self.expert_confidence +
            w["bootstrap"] * self.bootstrap_stability
        )
        return self.combined_score


@dataclass
class ExpertReview:
    """A hydrologist's review of an edge."""
    reviewer_id: str
    reviewer_name: str
    edge_key: str  # "source -> target"
    is_valid: bool
    confidence: float  # 0-1
    mechanism_note: str = ""
    suggested_lag: Optional[int] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ValidationReport:
    """Complete DAG validation report."""
    dag_version: str
    validation_timestamp: str
    total_edges: int
    edges_validated: int
    edges_accepted: int
    edges_rejected: int
    edges_modified: int
    mean_combined_score: float
    min_combined_score: float
    dag_is_acyclic: bool
    expert_reviews: list[ExpertReview]
    edge_scores: list[dict]
    report_hash: str = ""

    def compute_hash(self) -> str:
        """Compute integrity hash for the report."""
        content = json.dumps(asdict(self), sort_keys=True, default=str)
        self.report_hash = hashlib.sha256(content.encode()).hexdigest()
        return self.report_hash


# ═══════════════════════════════════════════════════════════════════
# PC Algorithm Implementation
# ═══════════════════════════════════════════════════════════════════

class PCAlgorithm:
    """
    PC algorithm for causal structure discovery.

    Uses conditional independence tests to discover causal edges
    from observational flood data. The discovered skeleton is
    compared against the expert-defined DAG.
    """

    def __init__(self, alpha: float = 0.05, max_cond_set: int = 3):
        """
        Args:
            alpha: Significance level for independence tests
            max_cond_set: Maximum conditioning set size
        """
        self.alpha = alpha
        self.max_cond_set = max_cond_set

    def conditional_independence_test(
        self,
        data: np.ndarray,
        x: int,
        y: int,
        conditioning_set: list[int],
    ) -> tuple[float, bool]:
        """
        Fisher's Z conditional independence test.

        Returns:
            (p_value, is_independent)
        """
        n = data.shape[0]

        if len(conditioning_set) == 0:
            # Marginal correlation
            r = np.corrcoef(data[:, x], data[:, y])[0, 1]
        else:
            # Partial correlation via regression residuals
            Z = data[:, conditioning_set]
            X = data[:, x]
            Y = data[:, y]

            # Residuals of X regressed on Z
            Z_pinv = np.linalg.pinv(Z)
            X_res = X - Z @ Z_pinv @ X
            Y_res = Y - Z @ Z_pinv @ Y

            if np.std(X_res) < 1e-10 or np.std(Y_res) < 1e-10:
                return 1.0, True

            r = np.corrcoef(X_res, Y_res)[0, 1]

        # Fisher's Z transformation
        r = np.clip(r, -0.9999, 0.9999)
        z = 0.5 * np.log((1 + r) / (1 - r))
        se = 1.0 / np.sqrt(n - len(conditioning_set) - 3)
        z_stat = abs(z) / se

        # Two-sided p-value from standard normal
        from scipy import stats
        p_value = 2 * (1 - stats.norm.cdf(z_stat))

        return p_value, p_value > self.alpha

    def discover_skeleton(
        self,
        data: np.ndarray,
        variable_names: list[str],
    ) -> dict[str, float]:
        """
        Discover the causal skeleton using the PC algorithm.

        Returns:
            dict mapping "source -> target" to data confidence score
        """
        n_vars = data.shape[1]
        adjacency = np.ones((n_vars, n_vars), dtype=bool)
        np.fill_diagonal(adjacency, False)

        sep_sets = {}
        edge_pvalues = {}

        for cond_size in range(self.max_cond_set + 1):
            for x in range(n_vars):
                for y in range(x + 1, n_vars):
                    if not adjacency[x, y]:
                        continue

                    # Get neighbors of x excluding y
                    neighbors = [
                        z for z in range(n_vars)
                        if z != x and z != y and adjacency[x, z]
                    ]

                    if len(neighbors) < cond_size:
                        continue

                    # Test all conditioning sets of given size
                    from itertools import combinations
                    for cond_set in combinations(neighbors, cond_size):
                        p_val, is_indep = self.conditional_independence_test(
                            data, x, y, list(cond_set)
                        )

                        if is_indep:
                            adjacency[x, y] = False
                            adjacency[y, x] = False
                            sep_sets[(x, y)] = list(cond_set)
                            break
                        else:
                            key = f"{variable_names[x]} -> {variable_names[y]}"
                            edge_pvalues[key] = min(
                                edge_pvalues.get(key, 1.0), p_val
                            )

        # Convert p-values to confidence scores
        edge_confidence = {}
        for x in range(n_vars):
            for y in range(n_vars):
                if x != y and adjacency[x, y]:
                    key = f"{variable_names[x]} -> {variable_names[y]}"
                    # Lower p-value = higher confidence in dependence
                    p_val = edge_pvalues.get(key, self.alpha)
                    edge_confidence[key] = 1.0 - p_val

        return edge_confidence


# ═══════════════════════════════════════════════════════════════════
# Bootstrap Stability Analysis
# ═══════════════════════════════════════════════════════════════════

def bootstrap_stability(
    data: np.ndarray,
    variable_names: list[str],
    n_bootstrap: int = 100,
    alpha: float = 0.05,
    sample_fraction: float = 0.8,
) -> dict[str, float]:
    """
    Run PC algorithm on bootstrap samples to assess edge stability.

    Returns:
        dict mapping edge key to fraction of bootstrap samples
        where the edge was discovered
    """
    n_samples = data.shape[0]
    sample_size = int(n_samples * sample_fraction)
    edge_counts: dict[str, int] = {}

    pc = PCAlgorithm(alpha=alpha)

    for i in range(n_bootstrap):
        # Bootstrap resample
        indices = np.random.choice(n_samples, size=sample_size, replace=True)
        boot_data = data[indices]

        try:
            edges = pc.discover_skeleton(boot_data, variable_names)
            for edge_key in edges:
                edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1
        except Exception as e:
            logger.warning(f"Bootstrap iteration {i} failed: {e}")

    # Convert counts to fractions
    return {
        key: count / n_bootstrap
        for key, count in edge_counts.items()
    }


# ═══════════════════════════════════════════════════════════════════
# DAG Validator
# ═══════════════════════════════════════════════════════════════════

class CausalDAGValidator:
    """
    Validates the Brahmaputra causal DAG against:
      1. Data-driven PC algorithm results
      2. Expert hydrologist reviews
      3. Bootstrap stability analysis
    """

    def __init__(
        self,
        dag_path: str = "data/brahmaputra_dag.json",
        acceptance_threshold: float = 0.5,
        score_weights: dict = None,
    ):
        self.dag_path = Path(dag_path)
        self.acceptance_threshold = acceptance_threshold
        self.score_weights = score_weights or {
            "data": 0.4,
            "expert": 0.4,
            "bootstrap": 0.2,
        }
        self.edges: list[CausalEdge] = []
        self.expert_reviews: list[ExpertReview] = []
        self.variable_names: list[str] = []
        self._load_dag()

    def _load_dag(self):
        """Load the expert-defined DAG from JSON."""
        if not self.dag_path.exists():
            logger.warning(f"DAG file not found: {self.dag_path}")
            self._create_default_dag()
            return

        with open(self.dag_path) as f:
            dag_data = json.load(f)

        self.variable_names = dag_data.get("variables", [])

        for edge_data in dag_data.get("edges", []):
            self.edges.append(CausalEdge(
                source=edge_data["source"],
                target=edge_data["target"],
                lag_hours=edge_data.get("lag_hours", 0),
                mechanism=edge_data.get("mechanism", ""),
                expert_confidence=edge_data.get("expert_confidence", 0.8),
            ))

        logger.info(
            f"Loaded DAG: {len(self.variable_names)} variables, "
            f"{len(self.edges)} edges"
        )

    def _create_default_dag(self):
        """Create default Brahmaputra river basin causal DAG."""
        self.variable_names = [
            "upstream_rainfall",
            "snowmelt_rate",
            "upstream_water_level",
            "tributary_inflow",
            "soil_moisture",
            "downstream_water_level",
            "flood_risk",
        ]

        default_edges = [
            ("upstream_rainfall", "upstream_water_level", 6,
             "Precipitation runoff into river channel"),
            ("snowmelt_rate", "upstream_water_level", 24,
             "Glacial/snow melt feeds river flow"),
            ("upstream_water_level", "downstream_water_level", 12,
             "Hydraulic wave propagation downstream"),
            ("tributary_inflow", "downstream_water_level", 8,
             "Tributary confluence increases main channel flow"),
            ("upstream_rainfall", "soil_moisture", 2,
             "Rainfall saturates soil reducing infiltration"),
            ("soil_moisture", "downstream_water_level", 4,
             "Saturated soil increases surface runoff"),
            ("downstream_water_level", "flood_risk", 1,
             "High water levels directly cause flooding"),
        ]

        for src, tgt, lag, mechanism in default_edges:
            self.edges.append(CausalEdge(
                source=src,
                target=tgt,
                lag_hours=lag,
                mechanism=mechanism,
                expert_confidence=0.8,
            ))

        # Save default DAG
        self._save_dag()

    def _save_dag(self):
        """Save current DAG to JSON."""
        dag_data = {
            "variables": self.variable_names,
            "edges": [asdict(e) for e in self.edges],
            "metadata": {
                "last_validated": datetime.now(timezone.utc).isoformat(),
                "n_edges": len(self.edges),
                "n_variables": len(self.variable_names),
            },
        }

        self.dag_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.dag_path, "w") as f:
            json.dump(dag_data, f, indent=2)

        logger.info(f"DAG saved to {self.dag_path}")

    def run_pc_algorithm(self, data: np.ndarray) -> dict[str, float]:
        """
        Run PC algorithm on observational data to get data-driven
        confidence scores for each edge.
        """
        pc = PCAlgorithm(alpha=0.05, max_cond_set=3)
        discovered = pc.discover_skeleton(data, self.variable_names)

        # Map discovered edges to existing DAG edges
        for edge in self.edges:
            key = f"{edge.source} -> {edge.target}"
            edge.data_confidence = discovered.get(key, 0.0)

        logger.info(f"PC algorithm: {len(discovered)} edges discovered")
        return discovered

    def run_bootstrap_analysis(
        self,
        data: np.ndarray,
        n_bootstrap: int = 100,
    ) -> dict[str, float]:
        """Run bootstrap stability analysis."""
        stability = bootstrap_stability(
            data, self.variable_names,
            n_bootstrap=n_bootstrap,
        )

        for edge in self.edges:
            key = f"{edge.source} -> {edge.target}"
            edge.bootstrap_stability = stability.get(key, 0.0)

        logger.info(f"Bootstrap: {n_bootstrap} iterations completed")
        return stability

    def add_expert_review(self, review: ExpertReview):
        """Add an expert hydrologist's review for an edge."""
        self.expert_reviews.append(review)

        # Update edge confidence
        for edge in self.edges:
            key = f"{edge.source} -> {edge.target}"
            if key == review.edge_key:
                edge.expert_confidence = review.confidence
                if review.mechanism_note:
                    edge.mechanism = review.mechanism_note
                if review.suggested_lag is not None:
                    edge.lag_hours = review.suggested_lag
                break

        logger.info(
            f"Expert review added: {review.reviewer_name} on {review.edge_key} "
            f"(valid={review.is_valid}, confidence={review.confidence})"
        )

    def check_acyclicity(self) -> bool:
        """Verify the DAG has no cycles using topological sort (Kahn's)."""
        # Build adjacency list
        adj: dict[str, list[str]] = {v: [] for v in self.variable_names}
        in_degree: dict[str, int] = {v: 0 for v in self.variable_names}

        for edge in self.edges:
            if edge.source in adj and edge.target in in_degree:
                adj[edge.source].append(edge.target)
                in_degree[edge.target] += 1

        # Kahn's algorithm
        queue = [v for v, d in in_degree.items() if d == 0]
        visited = 0

        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        is_acyclic = visited == len(self.variable_names)
        if not is_acyclic:
            logger.error("CYCLE DETECTED in causal DAG!")
        return is_acyclic

    def compute_scores(self):
        """Compute combined confidence scores for all edges."""
        for edge in self.edges:
            edge.compute_combined_score(self.score_weights)

    def validate(
        self,
        data: Optional[np.ndarray] = None,
        n_bootstrap: int = 50,
    ) -> ValidationReport:
        """
        Run the complete validation pipeline:
          1. PC algorithm (if data provided)
          2. Bootstrap stability (if data provided)
          3. Compute combined scores
          4. Check acyclicity
          5. Generate report
        """
        if data is not None:
            logger.info("Running PC algorithm...")
            self.run_pc_algorithm(data)

            logger.info(f"Running bootstrap ({n_bootstrap} iterations)...")
            self.run_bootstrap_analysis(data, n_bootstrap=n_bootstrap)

        self.compute_scores()
        is_acyclic = self.check_acyclicity()

        # Classify edges
        accepted = [e for e in self.edges if e.combined_score >= self.acceptance_threshold]
        rejected = [e for e in self.edges if e.combined_score < self.acceptance_threshold]

        scores = [e.combined_score for e in self.edges]
        mean_score = np.mean(scores) if scores else 0.0
        min_score = np.min(scores) if scores else 0.0

        report = ValidationReport(
            dag_version=hashlib.md5(
                json.dumps([asdict(e) for e in self.edges]).encode()
            ).hexdigest()[:8],
            validation_timestamp=datetime.now(timezone.utc).isoformat(),
            total_edges=len(self.edges),
            edges_validated=len(self.edges),
            edges_accepted=len(accepted),
            edges_rejected=len(rejected),
            edges_modified=len([r for r in self.expert_reviews if r.suggested_lag]),
            mean_combined_score=float(mean_score),
            min_combined_score=float(min_score),
            dag_is_acyclic=is_acyclic,
            expert_reviews=self.expert_reviews,
            edge_scores=[
                {
                    "edge": f"{e.source} -> {e.target}",
                    "data_confidence": round(e.data_confidence, 3),
                    "expert_confidence": round(e.expert_confidence, 3),
                    "bootstrap_stability": round(e.bootstrap_stability, 3),
                    "combined_score": round(e.combined_score, 3),
                    "accepted": e.combined_score >= self.acceptance_threshold,
                    "lag_hours": e.lag_hours,
                    "mechanism": e.mechanism,
                }
                for e in self.edges
            ],
        )

        report.compute_hash()

        logger.info(
            f"Validation complete: {report.edges_accepted}/{report.total_edges} "
            f"edges accepted. Acyclic: {is_acyclic}. "
            f"Mean score: {mean_score:.3f}"
        )

        return report

    def export_validated_dag(self, output_path: Optional[str] = None) -> dict:
        """Export the validated DAG (only accepted edges) to JSON."""
        self.compute_scores()
        accepted = [
            e for e in self.edges
            if e.combined_score >= self.acceptance_threshold
        ]

        validated_dag = {
            "variables": self.variable_names,
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "lag_hours": e.lag_hours,
                    "mechanism": e.mechanism,
                    "combined_score": round(e.combined_score, 3),
                    "data_confidence": round(e.data_confidence, 3),
                    "expert_confidence": round(e.expert_confidence, 3),
                    "bootstrap_stability": round(e.bootstrap_stability, 3),
                }
                for e in accepted
            ],
            "metadata": {
                "validated_at": datetime.now(timezone.utc).isoformat(),
                "acceptance_threshold": self.acceptance_threshold,
                "total_edges_considered": len(self.edges),
                "edges_accepted": len(accepted),
                "score_weights": self.score_weights,
            },
        }

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(validated_dag, f, indent=2)
            logger.info(f"Validated DAG exported to {path}")

        return validated_dag


# ═══════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════

def main():
    """Run DAG validation with synthetic demo data."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Causal DAG Validation...")

    validator = CausalDAGValidator()

    # Generate synthetic observational data for demo
    np.random.seed(42)
    n_samples = 1000
    n_vars = len(validator.variable_names)

    # Create correlated data matching expected causal structure
    data = np.random.randn(n_samples, n_vars)
    # upstream_rainfall -> upstream_water_level
    data[:, 2] += 0.7 * np.roll(data[:, 0], 6)
    # snowmelt -> upstream_water_level
    data[:, 2] += 0.4 * np.roll(data[:, 1], 24)
    # upstream -> downstream
    data[:, 5] += 0.8 * np.roll(data[:, 2], 12)
    # tributary -> downstream
    data[:, 5] += 0.5 * np.roll(data[:, 3], 8)
    # rainfall -> soil moisture
    data[:, 4] += 0.6 * np.roll(data[:, 0], 2)
    # soil -> downstream
    data[:, 5] += 0.3 * np.roll(data[:, 4], 4)
    # downstream -> flood_risk
    data[:, 6] += 0.9 * np.roll(data[:, 5], 1)

    # Add expert review
    validator.add_expert_review(ExpertReview(
        reviewer_id="expert-001",
        reviewer_name="Dr. Pankaj Sharma (IIT Guwahati)",
        edge_key="upstream_rainfall -> upstream_water_level",
        is_valid=True,
        confidence=0.95,
        mechanism_note="Primary driver of monsoon flooding in Brahmaputra basin",
        suggested_lag=6,
    ))

    validator.add_expert_review(ExpertReview(
        reviewer_id="expert-002",
        reviewer_name="Dr. Ritu Bora (CWC Guwahati)",
        edge_key="upstream_water_level -> downstream_water_level",
        is_valid=True,
        confidence=0.90,
        mechanism_note="Hydraulic wave propagation — 12h lag consistent with station data",
    ))

    # Run validation
    report = validator.validate(data=data, n_bootstrap=50)

    # Print results
    print("\n" + "=" * 60)
    print("ARGUS — Causal DAG Validation Report")
    print("=" * 60)
    print(f"DAG Version:     {report.dag_version}")
    print(f"Timestamp:       {report.validation_timestamp}")
    print(f"Acyclic:         {'✓' if report.dag_is_acyclic else '✗ CYCLE DETECTED'}")
    print(f"Edges Accepted:  {report.edges_accepted}/{report.total_edges}")
    print(f"Mean Score:      {report.mean_combined_score:.3f}")
    print(f"Min Score:       {report.min_combined_score:.3f}")
    print(f"Report Hash:     {report.report_hash[:16]}...")
    print()

    for es in report.edge_scores:
        status = "✓" if es["accepted"] else "✗"
        print(
            f"  {status} {es['edge']:50s} "
            f"combined={es['combined_score']:.3f} "
            f"(data={es['data_confidence']:.3f} "
            f"expert={es['expert_confidence']:.3f} "
            f"boot={es['bootstrap_stability']:.3f})"
        )

    print()

    # Export validated DAG
    validator.export_validated_dag("data/brahmaputra_dag_validated.json")

    # Save report
    report_path = Path("data/dag_validation_report.json")
    with open(report_path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)
    print(f"Full report saved to {report_path}")


if __name__ == "__main__":
    main()
