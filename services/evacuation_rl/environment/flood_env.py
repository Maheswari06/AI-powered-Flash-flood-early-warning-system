"""PettingZoo multi-agent flood evacuation environment.

Agents: one coordinator per district (Majuli, Jorhat)
State: villages at risk, vehicles, shelter capacity, road closures, time
Action: assign vehicle V to village U via route R
Reward: +10 per person evacuated, penalties for conflicts, overflow, empty trips
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Try PettingZoo; fall back to standalone
try:
    from pettingzoo import AECEnv
    from pettingzoo.utils import agent_selector

    _PETTINGZOO = True
except ImportError:
    _PETTINGZOO = False

try:
    import gymnasium as gym
    from gymnasium import spaces

    _GYM = True
except ImportError:
    _GYM = False


# ── Helpers ──────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Environment ──────────────────────────────────────────────────────────

class FloodEvacuationEnv:
    """Multi-agent flood evacuation environment (PettingZoo-compatible).

    Works with or without PettingZoo/Gymnasium installed.
    """

    metadata = {"render_modes": ["human", "rgb_array"], "name": "flood_evacuation_v1"}

    def __init__(self, config_path: str = "./data/majuli_evacuation_config.json"):
        self.config = self._load_config(config_path)
        self.possible_agents = ["coordinator_majuli", "coordinator_jorhat"]
        self.agent_name_mapping = {a: i for i, a in enumerate(self.possible_agents)}

        # Parse config
        self.villages = self.config.get("villages", [])
        self.vehicles = self.config.get("vehicles", [])
        self.shelters = self.config.get("shelters", [])
        self.roads = self.config.get("roads", [])
        self.total_time = self.config.get("total_time_minutes", 120)
        self.flood_arrival = self.config.get("flood_arrival_by_village", {})

        n_vehicles = len(self.vehicles)
        n_villages = len(self.villages)
        n_routes = len(self.roads)

        # Action space: (vehicle_idx, village_idx, route_idx)
        self._action_space_size = max(1, n_vehicles * n_villages * n_routes)

        if _GYM:
            obs_dim = self._compute_obs_dim()
            self._action_spaces = {
                a: spaces.Discrete(self._action_space_size) for a in self.possible_agents
            }
            self._observation_spaces = {
                a: spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
                for a in self.possible_agents
            }

        self.reset()

    def _load_config(self, path: str) -> Dict:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
        logger.warning("config_not_found_using_defaults", path=path)
        return {
            "scenario_name": "default",
            "total_time_minutes": 120,
            "flood_arrival_by_village": {},
            "villages": [],
            "vehicles": [],
            "shelters": [],
            "roads": [],
        }

    def _compute_obs_dim(self) -> int:
        # village features (risk, pop, evacuated) + vehicle (available, lat, lon) + shelter occupancy + time
        return len(self.villages) * 3 + len(self.vehicles) * 3 + len(self.shelters) + 2

    def reset(self, seed: int | None = None, options: dict | None = None):
        if seed is not None:
            np.random.seed(seed)

        self.current_time = 0  # minutes since alert
        self.done = False

        # Village state
        self.village_pop_remaining = {v["id"]: v["population"] for v in self.villages}
        self.village_evacuated = {v["id"]: 0 for v in self.villages}

        # Vehicle state
        self.vehicle_available_at = {v["id"]: 0 for v in self.vehicles}  # time when available
        self.vehicle_trips = {v["id"]: 0 for v in self.vehicles}

        # Shelter state
        self.shelter_occupancy = {s["id"]: 0 for s in self.shelters}

        # Road state
        self.road_vehicles = {r["id"]: [] for r in self.roads}  # vehicles on road

        # Agent tracking
        self.agents = list(self.possible_agents)
        self._agent_idx = 0

        # Metrics
        self.total_evacuated = 0
        self.road_conflicts = 0
        self.shelter_overflows = 0
        self.empty_trips = 0
        self.total_reward = 0.0

        obs = self._get_obs()
        return obs, {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Execute vehicle assignment action."""
        if self.done:
            return self._get_obs(), 0.0, True, False, {}

        reward = 0.0
        info: Dict[str, Any] = {}

        # Decode action
        n_v = max(len(self.vehicles), 1)
        n_vil = max(len(self.villages), 1)
        n_r = max(len(self.roads), 1)

        vehicle_idx = action // (n_vil * n_r)
        remainder = action % (n_vil * n_r)
        village_idx = remainder // n_r
        route_idx = remainder % n_r

        vehicle_idx = min(vehicle_idx, len(self.vehicles) - 1)
        village_idx = min(village_idx, len(self.villages) - 1)
        route_idx = min(route_idx, len(self.roads) - 1)

        vehicle = self.vehicles[vehicle_idx]
        village = self.villages[village_idx]
        road = self.roads[route_idx]

        info["vehicle"] = vehicle["id"]
        info["village"] = village["id"]
        info["road"] = road["id"]

        # Check vehicle availability
        if self.vehicle_available_at[vehicle["id"]] > self.current_time:
            reward -= 1.0  # vehicle busy
            info["blocked"] = "vehicle_busy"
        else:
            # Check road safety
            if not self._is_road_safe(road["id"], self.current_time):
                reward -= 3.0
                info["blocked"] = "road_closed"
            else:
                # Compute travel time
                travel_time = road["distance_km"] / vehicle["avg_speed_kmh"] * 60  # minutes

                # Check if vehicle arrives before flood
                arrival_time = self.current_time + travel_time
                flood_time = self.flood_arrival.get(village["id"], self.total_time)

                if arrival_time < flood_time:
                    # Successful pickup
                    pop_remaining = self.village_pop_remaining[village["id"]]
                    people_moved = min(pop_remaining, vehicle["capacity"])

                    if people_moved < vehicle["capacity"] * 0.2 and people_moved > 0:
                        reward -= 2.0  # empty trip penalty
                        self.empty_trips += 1

                    if people_moved > 0:
                        # Check road conflict (2+ vehicles on same road)
                        if len(self.road_vehicles[road["id"]]) > 0:
                            reward -= 5.0
                            self.road_conflicts += 1

                        # Find nearest shelter
                        shelter = self._find_shelter(village)
                        if shelter:
                            new_occ = self.shelter_occupancy[shelter["id"]] + people_moved
                            if new_occ > shelter["capacity"]:
                                reward -= 8.0
                                self.shelter_overflows += 1
                            self.shelter_occupancy[shelter["id"]] = new_occ

                        # Evacuate
                        self.village_pop_remaining[village["id"]] -= people_moved
                        self.village_evacuated[village["id"]] += people_moved
                        self.total_evacuated += people_moved
                        reward += people_moved * 10.0 / max(village["population"], 1)

                        # Time bonus
                        buffer = flood_time - arrival_time
                        if buffer > 30:
                            reward += 3.0

                        # Update vehicle
                        return_time = travel_time * 2  # round trip
                        self.vehicle_available_at[vehicle["id"]] = self.current_time + return_time
                        self.vehicle_trips[vehicle["id"]] += 1

                        info["moved"] = people_moved
                        info["eta_min"] = round(travel_time, 1)
                        info["buffer_min"] = round(buffer, 1)
                        info["shelter"] = shelter["id"] if shelter else None
                    else:
                        info["blocked"] = "village_empty"
                else:
                    reward -= 5.0
                    info["blocked"] = "too_late"

        # Advance time
        self.current_time += 5  # 5-minute time steps

        # Check termination
        all_evacuated = all(p <= 0 for p in self.village_pop_remaining.values())
        time_up = self.current_time >= self.total_time
        terminated = all_evacuated
        truncated = time_up and not all_evacuated

        self.done = terminated or truncated
        self.total_reward += reward

        info.update({
            "time": self.current_time,
            "total_evacuated": self.total_evacuated,
            "total_remaining": sum(self.village_pop_remaining.values()),
        })

        return self._get_obs(), reward, terminated, truncated, info

    def _is_road_safe(self, road_id: str, departure_time: int) -> bool:
        for road in self.roads:
            if road["id"] == road_id:
                return departure_time < road.get("closes_at_minutes", self.total_time)
        return True

    def _find_shelter(self, village: Dict) -> Optional[Dict]:
        """Find nearest shelter with capacity."""
        best = None
        best_dist = float("inf")
        for s in self.shelters:
            if self.shelter_occupancy[s["id"]] < s["capacity"]:
                d = _haversine_km(village["lat"], village["lon"], s["lat"], s["lon"])
                if d < best_dist:
                    best_dist = d
                    best = s
        return best

    def _get_obs(self) -> np.ndarray:
        obs = []
        for v in self.villages:
            obs.append(v["risk_score"])
            obs.append(self.village_pop_remaining[v["id"]] / max(v["population"], 1))
            obs.append(self.village_evacuated[v["id"]] / max(v["population"], 1))
        for veh in self.vehicles:
            obs.append(1.0 if self.vehicle_available_at[veh["id"]] <= self.current_time else 0.0)
            obs.append(veh["depot_lat"] / 30.0)
            obs.append(veh["depot_lon"] / 100.0)
        for s in self.shelters:
            obs.append(self.shelter_occupancy[s["id"]] / max(s["capacity"], 1))
        obs.append(self.current_time / self.total_time)
        obs.append(self.total_evacuated / max(sum(v["population"] for v in self.villages), 1))
        return np.array(obs, dtype=np.float32)

    def get_state_summary(self) -> Dict:
        return {
            "current_time_min": self.current_time,
            "total_evacuated": self.total_evacuated,
            "total_remaining": sum(self.village_pop_remaining.values()),
            "total_population": sum(v["population"] for v in self.villages),
            "road_conflicts": self.road_conflicts,
            "shelter_overflows": self.shelter_overflows,
            "empty_trips": self.empty_trips,
            "total_reward": round(self.total_reward, 2),
            "village_status": {
                v["id"]: {
                    "remaining": self.village_pop_remaining[v["id"]],
                    "evacuated": self.village_evacuated[v["id"]],
                    "flood_arrival_min": self.flood_arrival.get(v["id"], self.total_time),
                }
                for v in self.villages
            },
            "shelter_status": {
                s["id"]: {
                    "occupancy": self.shelter_occupancy[s["id"]],
                    "capacity": s["capacity"],
                }
                for s in self.shelters
            },
        }
