"""Causal GNN — Graph Neural Network for causal flood inference.

Implements a lightweight GCN that propagates causal signals through
the DAG.  Falls back to a NumPy structural-equation simulator when
PyTorch Geometric is not available.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from shared.models.phase2 import CausalDAG, CausalEdge

logger = structlog.get_logger(__name__)

# ── Try importing PyTorch Geometric ──────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    logger.warning("torch_unavailable", msg="Using NumPy SEM fallback")


# ══════════════════════════════════════════════════════════════════════════
#  NumPy fallback: Structural Equation Model (SEM) simulator
# ══════════════════════════════════════════════════════════════════════════

class SEMSimulator:
    """Forward-simulate a linear SEM over the DAG with NumPy."""

    def __init__(self, dag: CausalDAG):
        self.dag = dag
        self.node_ids = [n.node_id for n in dag.nodes]
        self.idx = {nid: i for i, nid in enumerate(self.node_ids)}
        self.n = len(self.node_ids)
        # Build adjacency weight matrix
        self.W = np.zeros((self.n, self.n), dtype=np.float32)
        for edge in dag.edges:
            si, ti = self.idx.get(edge.source), self.idx.get(edge.target)
            if si is not None and ti is not None:
                self.W[si, ti] = edge.weight

    def forward(self, evidence: Dict[str, float]) -> Dict[str, float]:
        """Propagate evidence through the DAG via topological pass."""
        values = np.zeros(self.n, dtype=np.float32)
        # Set evidence
        for var, val in evidence.items():
            if var in self.idx:
                values[self.idx[var]] = val

        # Topological sort (Kahn's algorithm)
        in_degree = np.sum(self.W > 0, axis=0).astype(int)
        queue = [i for i in range(self.n) if in_degree[i] == 0]
        order: List[int] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for j in range(self.n):
                if self.W[node, j] > 0:
                    in_degree[j] -= 1
                    if in_degree[j] == 0:
                        queue.append(j)

        # Forward pass
        for i in order:
            nid = self.node_ids[i]
            if nid in evidence:
                continue  # fixed evidence
            parent_signal = 0.0
            for pi in range(self.n):
                if self.W[pi, i] > 0:
                    parent_signal += self.W[pi, i] * values[pi]
            values[i] = float(1.0 / (1.0 + math.exp(-parent_signal)))  # sigmoid

        return {self.node_ids[i]: float(values[i]) for i in range(self.n)}

    def intervene(
        self, do_var: str, do_val: float, evidence: Dict[str, float]
    ) -> Dict[str, float]:
        """do(X=x): cut incoming edges to X, fix its value, propagate."""
        # Temporarily zero-out incoming edges to do_var
        original_col = self.W[:, self.idx[do_var]].copy()
        self.W[:, self.idx[do_var]] = 0.0
        evidence_copy = {**evidence, do_var: do_val}
        result = self.forward(evidence_copy)
        # Restore edges
        self.W[:, self.idx[do_var]] = original_col
        return result


# ══════════════════════════════════════════════════════════════════════════
#  PyTorch GCN model (used when torch is available)
# ══════════════════════════════════════════════════════════════════════════

if _TORCH_AVAILABLE:

    class CausalGCNLayer(nn.Module):
        """Single GCN message-passing layer with causal edge weights."""

        def __init__(self, in_features: int, out_features: int):
            super().__init__()
            self.linear = nn.Linear(in_features, out_features)

        def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
            # Degree-normalised message passing: D^{-1} A X W
            deg = adj.sum(dim=1, keepdim=True).clamp(min=1.0)
            norm_adj = adj / deg
            support = self.linear(x)
            return F.relu(norm_adj @ support)

    class CausalGCN(nn.Module):
        """Multi-layer GCN for causal flood risk inference."""

        def __init__(self, n_nodes: int, hidden: int = 64, n_layers: int = 3):
            super().__init__()
            self.embed = nn.Linear(1, hidden)
            self.layers = nn.ModuleList(
                [CausalGCNLayer(hidden, hidden) for _ in range(n_layers)]
            )
            self.head = nn.Linear(hidden, 1)

        def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
            h = F.relu(self.embed(x))
            for layer in self.layers:
                h = layer(h, adj) + h  # residual
            return torch.sigmoid(self.head(h))


# ══════════════════════════════════════════════════════════════════════════
#  Unified CausalGNNEngine (wraps GCN or SEM)
# ══════════════════════════════════════════════════════════════════════════

class CausalGNNEngine:
    """High-level API: wraps torch GCN or NumPy SEM transparently."""

    def __init__(self, dag: CausalDAG, hidden: int = 64, n_layers: int = 3):
        self.dag = dag
        self.sem = SEMSimulator(dag)
        self.node_ids = [n.node_id for n in dag.nodes]
        self.idx = {nid: i for i, nid in enumerate(self.node_ids)}
        self.n = len(self.node_ids)
        self._use_torch = _TORCH_AVAILABLE

        if self._use_torch:
            self.model = CausalGCN(self.n, hidden, n_layers)
            self.model.eval()
            # Build adjacency tensor from DAG
            adj_np = np.zeros((self.n, self.n), dtype=np.float32)
            for edge in dag.edges:
                si, ti = self.idx.get(edge.source), self.idx.get(edge.target)
                if si is not None and ti is not None:
                    adj_np[si, ti] = edge.weight
            self.adj = torch.tensor(adj_np)
            logger.info("causal_gcn_ready", nodes=self.n, edges=len(dag.edges))
        else:
            self.model = None
            self.adj = None
            logger.info("causal_sem_ready", nodes=self.n, edges=len(dag.edges))

    def predict(self, evidence: Dict[str, float]) -> Dict[str, float]:
        """Forward pass: predict all node values given evidence."""
        if self._use_torch:
            x = torch.zeros(self.n, 1)
            for var, val in evidence.items():
                if var in self.idx:
                    x[self.idx[var], 0] = val
            with torch.no_grad():
                out = self.model(x, self.adj)
            return {self.node_ids[i]: float(out[i, 0]) for i in range(self.n)}
        return self.sem.forward(evidence)

    def intervene(
        self,
        do_var: str,
        do_val: float,
        evidence: Dict[str, float],
        targets: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """do(X=x) — returns (original_values, counterfactual_values)."""
        original = self.predict(evidence)
        if self._use_torch:
            # Remove incoming edges to do_var, fix value
            adj_copy = self.adj.clone()
            adj_copy[:, self.idx[do_var]] = 0.0
            x = torch.zeros(self.n, 1)
            for var, val in evidence.items():
                if var in self.idx:
                    x[self.idx[var], 0] = val
            x[self.idx[do_var], 0] = do_val
            with torch.no_grad():
                out = self.model(x, adj_copy)
            cf = {self.node_ids[i]: float(out[i, 0]) for i in range(self.n)}
        else:
            cf = self.sem.intervene(do_var, do_val, evidence)

        if targets:
            original = {k: v for k, v in original.items() if k in targets}
            cf = {k: v for k, v in cf.items() if k in targets}
        return original, cf

    def get_adjacency_dict(self) -> Dict[str, Dict[str, float]]:
        """Return adjacency as {source: {target: weight}}."""
        adj: Dict[str, Dict[str, float]] = {}
        for edge in self.dag.edges:
            adj.setdefault(edge.source, {})[edge.target] = edge.weight
        return adj
