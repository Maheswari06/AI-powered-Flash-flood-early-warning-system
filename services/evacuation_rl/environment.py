"""Gymnasium environment for flood evacuation planning.

State:  [zone_populations... | route_passable... | flood_risk | time_remaining]
Action: Discrete — which (zone, route) pair to prioritise next
Reward: + for people reaching safety, – for casualties / time penalty
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from services.evacuation_rl.graph import EvacuationGraph

logger = structlog.get_logger(__name__)

# Try Gymnasium; fall back to a shimmed interface
try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except ImportError:
    _GYM_AVAILABLE = False


class EvacuationEnv:
    """Custom Gymnasium-compatible environment for evacuation RL.

    Works with or without the gymnasium package installed.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        graph: EvacuationGraph,
        village_id: str = "kullu_01",
        max_steps: int = 30,
        initial_risk: float = 0.6,
    ):
        self.graph = graph
        self.village_id = village_id
        self.max_steps = max_steps
        self.initial_risk = initial_risk

        # Get relevant zones and routes
        self.pop_zones = graph.get_populated_zones(village_id)
        self.safe_zones = graph.get_safe_zones(village_id)
        self.all_zones = self.pop_zones + self.safe_zones

        # Build action space: each (source_zone, route) pair
        self.actions: List[Tuple[str, str]] = []
        for zone in self.pop_zones:
            for route, dest in graph.get_routes_from(zone.zone_id):
                self.actions.append((zone.zone_id, route.route_id))

        self.n_actions = max(len(self.actions), 1)

        # State dimensions
        n_zones = len(self.all_zones)
        n_routes = len([r for z in self.pop_zones for r, _ in graph.get_routes_from(z.zone_id)])
        self.state_dim = n_zones + n_routes + 2  # +2 for risk, time_remaining

        # Spaces (Gym-compatible)
        if _GYM_AVAILABLE:
            self.observation_space = spaces.Box(
                low=0.0, high=1.0, shape=(self.state_dim,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(self.n_actions)

        # Internal state
        self._step = 0
        self._populations: Dict[str, int] = {}
        self._safe_arrivals: int = 0
        self._risk: float = initial_risk
        self._done = False

    def reset(self, seed: int | None = None) -> Tuple[np.ndarray, Dict]:
        """Reset environment to initial state."""
        if seed is not None:
            np.random.seed(seed)
        self._step = 0
        self._safe_arrivals = 0
        self._risk = self.initial_risk
        self._done = False
        self._populations = {z.zone_id: z.population for z in self.pop_zones}
        obs = self._get_obs()
        return obs, {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Execute an evacuation action.

        Returns: (obs, reward, terminated, truncated, info)
        """
        reward = 0.0
        info: Dict[str, Any] = {}

        if self._done:
            return self._get_obs(), 0.0, True, False, info

        # Decode action
        if action < len(self.actions):
            zone_id, route_id = self.actions[action]
            route = self.graph._route_map.get(route_id)
            zone = self.graph._zone_map.get(zone_id)

            if route and zone and route.is_passable:
                # Move people along route
                available = self._populations.get(zone_id, 0)
                # People moved this step: limited by route capacity / max_steps
                move_capacity = max(1, route.capacity_persons_hr // self.max_steps)
                moved = min(available, move_capacity)
                self._populations[zone_id] = max(0, available - moved)
                self._safe_arrivals += moved
                reward += moved * 0.1  # reward per person evacuated

                info["moved"] = moved
                info["from_zone"] = zone_id
                info["route"] = route_id
            else:
                # Route blocked or invalid
                reward -= 0.5
                info["blocked"] = True
        else:
            reward -= 0.1  # invalid action

        # Time penalty
        self._step += 1
        reward -= 0.02  # slight urgency penalty per step

        # Risk escalation (simulates rising flood)
        self._risk = min(1.0, self._risk + 0.02 * np.random.uniform(0.5, 1.5))

        # Update route passability based on rising risk
        risk_dict = {self.village_id: self._risk}
        self.graph.update_flood_risk(risk_dict)

        # Casualty check: remaining pop in flooded zones
        if self._risk > 0.85:
            for zid in list(self._populations):
                if self._populations[zid] > 0:
                    casualties = int(self._populations[zid] * 0.05)
                    self._populations[zid] -= casualties
                    reward -= casualties * 1.0  # heavy penalty

        # Check termination
        total_remaining = sum(self._populations.values())
        terminated = total_remaining == 0 or self._step >= self.max_steps
        truncated = self._step >= self.max_steps and total_remaining > 0

        if terminated and total_remaining == 0:
            reward += 10.0  # bonus for full evacuation

        self._done = terminated or truncated

        info.update({
            "step": self._step,
            "risk": round(self._risk, 3),
            "safe_arrivals": self._safe_arrivals,
            "remaining": total_remaining,
        })

        return self._get_obs(), reward, terminated, truncated, info

    def _get_obs(self) -> np.ndarray:
        """Build normalised observation vector."""
        obs = []
        # Zone populations (normalised by max 1000)
        for z in self.all_zones:
            pop = self._populations.get(z.zone_id, 0)
            obs.append(min(1.0, pop / 1000))
        # Route passability
        for z in self.pop_zones:
            for route, _ in self.graph.get_routes_from(z.zone_id):
                obs.append(1.0 if route.is_passable else 0.0)
        # Risk and time
        obs.append(self._risk)
        obs.append(1.0 - self._step / self.max_steps)

        # Pad or truncate to state_dim
        while len(obs) < self.state_dim:
            obs.append(0.0)
        return np.array(obs[: self.state_dim], dtype=np.float32)

    def get_state_summary(self) -> Dict:
        """Human-readable state summary."""
        return {
            "step": self._step,
            "risk": round(self._risk, 3),
            "safe_arrivals": self._safe_arrivals,
            "remaining": sum(self._populations.values()),
            "populations": dict(self._populations),
            "total_actions": self.n_actions,
        }
