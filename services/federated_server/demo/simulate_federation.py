"""Federation demo script — simulates 3 nodes doing federated learning.

Shows on the dashboard: gradient updates flowing, global model improving
across Assam, Himachal Pradesh, and Bangladesh nodes.

Usage:
  python -m services.federated_server.demo.simulate_federation --rounds 3 --verbose

Output:
  Per-round accuracy improvement, gradient magnitudes per node.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Dict, List, Tuple

import numpy as np
import structlog

from services.federated_server.clients import (
    FloodMLP,
    generate_synthetic_data,
)
from services.federated_server.aggregator import (
    FederatedAggregator,
    create_synthetic_global_model,
)

logger = structlog.get_logger(__name__)


def simulate_local_training(
    node_id: str,
    global_weights: List[np.ndarray],
    n_samples: int = 500,
    epochs: int = 5,
) -> Tuple[List[np.ndarray], int, Dict]:
    """Simulate local training on one node."""
    model = FloodMLP()
    model.set_weights([w.copy() for w in global_weights])
    X, y = generate_synthetic_data(node_id, n_samples)
    loss = model.train(X, y, epochs=epochs)
    _, acc = model.evaluate(X, y)
    return model.get_weights(), n_samples, {"loss": loss, "accuracy": acc, "node": node_id}


def run_federation_demo(
    num_rounds: int = 3,
    nodes: List[str] = None,
    samples_per_node: int = 500,
    verbose: bool = True,
):
    """Run a complete federated learning simulation.

    Args:
        num_rounds: Number of federation rounds.
        nodes: List of node IDs (default: assam, himachal, bangladesh).
        samples_per_node: Training samples per node.
        verbose: Print per-round details.
    """
    if nodes is None:
        nodes = ["assam", "himachal", "bangladesh"]

    # Initialize global model
    init_weights = create_synthetic_global_model()
    aggregator = FederatedAggregator(
        global_weights=init_weights,
        method="fedprox",
        dp_epsilon=1.0,
        dp_delta=1e-5,
        clip_norm=1.0,
    )

    # Convert to list format for the MLP
    global_params = [init_weights[k] for k in sorted(init_weights.keys())]

    print(f"\n{'='*60}")
    print(f"  ARGUS Federated Learning Simulation")
    print(f"  Nodes: {', '.join(nodes)}")
    print(f"  Rounds: {num_rounds} | Samples/node: {samples_per_node}")
    print(f"  Strategy: FedProx (μ=0.1) + DP (ε=1.0)")
    print(f"{'='*60}\n")

    history = []

    for round_num in range(1, num_rounds + 1):
        round_results = []

        # Each node trains locally (simulated in threads for demo)
        for node_id in nodes:
            updated_weights, n_samples, metrics = simulate_local_training(
                node_id, global_params, samples_per_node
            )

            # Compute deltas (weight updates)
            deltas = {}
            for i, k in enumerate(sorted(init_weights.keys())):
                deltas[k] = updated_weights[i] - global_params[i]

            round_results.append((deltas, n_samples))

            if verbose:
                grad_norm = np.sqrt(sum(np.sum(d**2) for d in deltas.values()))
                print(f"  Round {round_num} | Node {node_id:12s} | "
                      f"loss={metrics['loss']:.4f} | "
                      f"acc={metrics['accuracy']:.3f} | "
                      f"||∇||={grad_norm:.4f}")

        # Aggregate
        new_global = aggregator.aggregate(round_results)
        global_params = [new_global[k] for k in sorted(new_global.keys())]

        # Evaluate global model on each node
        round_accs = []
        for node_id in nodes:
            model = FloodMLP()
            model.set_weights([w.copy() for w in global_params])
            X, y = generate_synthetic_data(node_id, samples_per_node)
            _, acc = model.evaluate(X, y)
            round_accs.append(acc)

        mean_acc = np.mean(round_accs)
        history.append({
            "round": round_num,
            "mean_accuracy": float(mean_acc),
            "per_node_accuracy": {n: a for n, a in zip(nodes, round_accs)},
            "privacy_spent": aggregator._privacy_budget_spent,
        })

        if verbose:
            print(f"  → Global model accuracy: {mean_acc:.3f} "
                  f"(privacy budget: ε={aggregator._privacy_budget_spent:.4f})\n")

    print(f"{'='*60}")
    print(f"  ✅ Federation complete after {num_rounds} rounds.")
    print(f"  Final global accuracy: {history[-1]['mean_accuracy']:.3f}")
    print(f"  Privacy budget spent: ε={aggregator._privacy_budget_spent:.4f}")
    print(f"  Global model updated with inputs from {len(nodes)} regions.")
    print(f"{'='*60}\n")

    return history


def main():
    parser = argparse.ArgumentParser(description="ARGUS Federated Learning Demo")
    parser.add_argument("--rounds", type=int, default=3, help="Number of federation rounds")
    parser.add_argument("--samples", type=int, default=500, help="Samples per node")
    parser.add_argument("--verbose", action="store_true", default=True, help="Print details")
    args = parser.parse_args()

    run_federation_demo(
        num_rounds=args.rounds,
        samples_per_node=args.samples,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
