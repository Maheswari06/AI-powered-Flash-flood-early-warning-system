"""Evacuation RL Agent — PPO or heuristic policy.

Uses Stable-Baselines3 PPO when available; falls back to a
greedy heuristic that prioritises zones by population × risk.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from services.evacuation_rl.environment import EvacuationEnv
from services.evacuation_rl.graph import EvacuationGraph
from shared.models.phase2 import EvacuationAction, EvacuationPlan

logger = structlog.get_logger(__name__)

# Try Stable-Baselines3
try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    logger.warning("sb3_unavailable", msg="Using heuristic evacuation policy")


class HeuristicPolicy:
    """Greedy heuristic: prioritise highest-population zones via shortest passable route."""

    def __init__(self, env: EvacuationEnv):
        self.env = env

    def predict(self, obs: np.ndarray, **kwargs) -> Tuple[int, None]:
        """Return action index (greedy: largest remaining pop, passable route)."""
        best_action = 0
        best_score = -1.0

        for i, (zone_id, route_id) in enumerate(self.env.actions):
            pop = self.env._populations.get(zone_id, 0)
            route = self.env.graph._route_map.get(route_id)
            if route and route.is_passable and pop > 0:
                # Score: population × route capacity × (1 - flood_risk)
                score = pop * route.capacity_persons_hr * (1 - route.flood_risk)
                if score > best_score:
                    best_score = score
                    best_action = i

        return best_action, None


class EvacuationAgent:
    """Evacuation RL agent with train/infer capabilities."""

    def __init__(
        self,
        graph: EvacuationGraph,
        village_id: str = "kullu_01",
        model_path: Optional[str] = None,
    ):
        self.graph = graph
        self.village_id = village_id
        self.model_path = model_path
        self.env = EvacuationEnv(graph, village_id)
        self._policy = None

        if _SB3_AVAILABLE and model_path and Path(model_path).exists():
            try:
                self._policy = PPO.load(model_path, env=self.env)
                logger.info("ppo_loaded", path=model_path)
            except Exception as e:
                logger.warning("ppo_load_failed", error=str(e))

        if self._policy is None:
            self._policy = HeuristicPolicy(self.env)
            logger.info("heuristic_policy_active")

    def train(self, total_timesteps: int = 10000) -> Dict:
        """Train a PPO agent (requires SB3)."""
        if not _SB3_AVAILABLE:
            return {"status": "skipped", "reason": "stable-baselines3 not installed"}

        self._policy = PPO(
            "MlpPolicy",
            self.env,
            verbose=0,
            learning_rate=3e-4,
            n_steps=256,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
        )
        self._policy.learn(total_timesteps=total_timesteps)

        if self.model_path:
            Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
            self._policy.save(self.model_path)
            logger.info("ppo_saved", path=self.model_path)

        return {
            "status": "trained",
            "timesteps": total_timesteps,
            "model_path": self.model_path,
        }

    def generate_plan(
        self,
        risk_score: float = 0.6,
        trigger_level: str = "WARNING",
    ) -> EvacuationPlan:
        """Run the agent through the environment and produce an evacuation plan."""
        self.env.initial_risk = risk_score
        obs, _ = self.env.reset()
        actions: List[EvacuationAction] = []
        total_reward = 0.0
        priority = 1

        for step in range(self.env.max_steps):
            action_idx, _ = self._policy.predict(obs)
            if isinstance(action_idx, np.ndarray):
                action_idx = int(action_idx[0])
            else:
                action_idx = int(action_idx)

            obs, reward, terminated, truncated, info = self.env.step(action_idx)
            total_reward += reward

            if action_idx < len(self.env.actions):
                zone_id, route_id = self.env.actions[action_idx]
                moved = info.get("moved", 0)
                if moved > 0:
                    route = self.graph._route_map.get(route_id)
                    actions.append(
                        EvacuationAction(
                            action_id=f"evac_{step}",
                            village_id=self.village_id,
                            zone_id=zone_id,
                            recommended_route=route_id,
                            priority=priority,
                            estimated_travel_min=route.travel_time_min if route else 0,
                            population_to_move=moved,
                            deadline_minutes=max(5, (self.env.max_steps - step) * 2),
                            confidence=max(0.3, 1.0 - info.get("risk", 0.5)),
                        )
                    )
                    priority += 1

            if terminated or truncated:
                break

        state = self.env.get_state_summary()
        plan = EvacuationPlan(
            plan_id=f"plan_{self.village_id}_{int(risk_score * 100)}",
            village_id=self.village_id,
            trigger_level=trigger_level,
            risk_score=risk_score,
            actions=actions,
            total_population=self.graph.total_population(self.village_id),
            estimated_clear_time_min=len(actions) * 5,
            zones_at_risk=len(self.env.pop_zones),
            safe_zones_available=len(self.env.safe_zones),
            rl_reward=round(total_reward, 3),
        )

        logger.info(
            "plan_generated",
            village=self.village_id,
            actions=len(actions),
            evacuated=state["safe_arrivals"],
            remaining=state["remaining"],
            reward=round(total_reward, 3),
        )
        return plan

    def evaluate(self, n_episodes: int = 10) -> Dict:
        """Evaluate policy over multiple episodes."""
        rewards = []
        evacuated_ratios = []

        for ep in range(n_episodes):
            obs, _ = self.env.reset(seed=ep)
            total_r = 0.0
            for _ in range(self.env.max_steps):
                action, _ = self._policy.predict(obs)
                if isinstance(action, np.ndarray):
                    action = int(action[0])
                obs, r, done, trunc, info = self.env.step(int(action))
                total_r += r
                if done or trunc:
                    break
            state = self.env.get_state_summary()
            total_pop = self.graph.total_population(self.village_id)
            ratio = state["safe_arrivals"] / max(1, total_pop)
            rewards.append(total_r)
            evacuated_ratios.append(ratio)

        return {
            "episodes": n_episodes,
            "mean_reward": round(float(np.mean(rewards)), 3),
            "std_reward": round(float(np.std(rewards)), 3),
            "mean_evacuation_ratio": round(float(np.mean(evacuated_ratios)), 3),
            "policy_type": "PPO" if _SB3_AVAILABLE and not isinstance(self._policy, HeuristicPolicy) else "heuristic",
        }
