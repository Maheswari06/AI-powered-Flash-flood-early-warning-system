"""ARGUS Phase 3 — Conditional DCGAN for Synthetic Flood Data.

Generates realistic synthetic flood-sensor time series conditioned on:
 • basin_id (one-hot)
 • season (monsoon / pre-monsoon / post-monsoon / winter)
 • severity_level (0.0 – 1.0)

Architecture:
  Generator:   z (100) + condition (8) → FC → Reshape → ConvTranspose1d × 3 → (12, 48)
  Discriminator: (12, 48) + condition (8) → Conv1d × 3 → FC → sigmoid

Output: 48-step × 12-feature synthetic sequences matching the feature engine schema.

In DEMO_MODE, returns precomputed synthetic batches from a parquet file or
hardcoded NumPy arrays — no GPU required.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

log = structlog.get_logger(__name__)

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# Feature names matching the feature engine schema
FEATURE_NAMES = [
    "rainfall_1h_mean",
    "water_level_6h_max",
    "soil_moisture_pct",
    "temperature_mean",
    "ndvi_index",
    "upstream_discharge_m3s",
    "dam_gate_pct",
    "tributary_confluence_level",
    "wind_speed_kmh",
    "barometric_pressure_hpa",
    "evapotranspiration_mm",
    "groundwater_depth_m",
]

BASIN_IDS = ["brahmaputra_upper", "beas_valley", "godavari_lower", "mahanadi_delta"]
SEASONS = ["monsoon", "pre_monsoon", "post_monsoon", "winter"]

# ── Demo data ────────────────────────────────────────────────────────────


def _generate_demo_sequence(
    severity: float = 0.7,
    season: str = "monsoon",
    steps: int = 48,
) -> np.ndarray:
    """Generate a single realistic-looking synthetic sequence."""
    rng = np.random.default_rng(42)
    n_features = len(FEATURE_NAMES)
    data = np.zeros((n_features, steps), dtype=np.float32)

    # Base patterns with seasonal modulation
    monsoon_factor = 1.5 if season == "monsoon" else 0.8
    t = np.linspace(0, 2 * np.pi, steps)

    # Rainfall: monsoon-heavy with noise
    data[0] = severity * 60.0 * monsoon_factor * (0.5 + 0.5 * np.sin(t)) + rng.normal(0, 5, steps)
    # Water level: lagged response to rainfall
    data[1] = severity * 9.0 * monsoon_factor * (0.3 + 0.7 * np.sin(t - 0.5)) + rng.normal(0, 0.3, steps)
    # Soil moisture
    data[2] = np.clip(50 + severity * 40 * monsoon_factor + rng.normal(0, 5, steps), 10, 100)
    # Temperature
    data[3] = 28 + 5 * np.sin(t * 2) + rng.normal(0, 1, steps)
    # NDVI
    data[4] = np.clip(0.6 - severity * 0.3 + rng.normal(0, 0.05, steps), 0, 1)
    # Upstream discharge
    data[5] = severity * 2000 * monsoon_factor * (0.4 + 0.6 * np.sin(t - 0.3)) + rng.normal(0, 100, steps)
    # Dam gate
    data[6] = np.clip(severity * 0.8 + rng.normal(0, 0.05, steps), 0, 1)
    # Tributary confluence
    data[7] = severity * 7 * monsoon_factor * (0.5 + 0.5 * np.sin(t - 0.7)) + rng.normal(0, 0.2, steps)
    # Wind speed
    data[8] = 15 + severity * 20 * np.sin(t) + rng.normal(0, 3, steps)
    # Barometric pressure
    data[9] = 1013 - severity * 15 + 5 * np.sin(t) + rng.normal(0, 2, steps)
    # Evapotranspiration
    data[10] = np.clip(3 + 2 * np.sin(t) + rng.normal(0, 0.5, steps), 0, 10)
    # Groundwater depth
    data[11] = np.clip(5 - severity * 3 + rng.normal(0, 0.3, steps), 0.5, 10)

    return np.clip(data, 0, None)


# ── GAN architecture (PyTorch) ───────────────────────────────────────────

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True

    class Generator(nn.Module):
        """Conditional 1D transposed-conv generator."""

        def __init__(self, z_dim: int = 100, cond_dim: int = 8, n_features: int = 12, seq_len: int = 48):
            super().__init__()
            self.seq_len = seq_len
            self.n_features = n_features

            self.fc = nn.Sequential(
                nn.Linear(z_dim + cond_dim, 256),
                nn.BatchNorm1d(256),
                nn.ReLU(True),
                nn.Linear(256, n_features * (seq_len // 4)),
                nn.BatchNorm1d(n_features * (seq_len // 4)),
                nn.ReLU(True),
            )

            self.conv = nn.Sequential(
                nn.ConvTranspose1d(n_features, 64, kernel_size=4, stride=2, padding=1),
                nn.BatchNorm1d(64),
                nn.ReLU(True),
                nn.ConvTranspose1d(64, n_features, kernel_size=4, stride=2, padding=1),
                nn.Tanh(),
            )

        def forward(self, z, cond):
            x = torch.cat([z, cond], dim=1)
            x = self.fc(x)
            x = x.view(-1, self.n_features, self.seq_len // 4)
            x = self.conv(x)
            return x

    class Discriminator(nn.Module):
        """Conditional 1D conv discriminator."""

        def __init__(self, n_features: int = 12, seq_len: int = 48, cond_dim: int = 8):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(n_features, 64, kernel_size=4, stride=2, padding=1),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv1d(64, 128, kernel_size=4, stride=2, padding=1),
                nn.BatchNorm1d(128),
                nn.LeakyReLU(0.2, inplace=True),
            )

            self.fc = nn.Sequential(
                nn.Linear(128 * (seq_len // 4) + cond_dim, 256),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(256, 1),
                nn.Sigmoid(),
            )

        def forward(self, x, cond):
            feat = self.conv(x)
            feat = feat.view(feat.size(0), -1)
            feat = torch.cat([feat, cond], dim=1)
            return self.fc(feat)

except ImportError:
    TORCH_AVAILABLE = False
    log.info("torch_not_available_gan_uses_numpy_fallback")


# ── GAN Generator Engine ────────────────────────────────────────────────

class FloodGANGenerator:
    """Generate synthetic flood data using trained GAN or demo fallback."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        self.checkpoint_path = checkpoint_path or os.getenv(
            "GAN_CHECKPOINT_PATH", "./models/flood_gan.pt"
        )
        self.generator = None
        self._load_model()

    def _load_model(self):
        """Load trained generator weights."""
        if not TORCH_AVAILABLE:
            log.info("gan_using_numpy_fallback")
            return

        if DEMO_MODE:
            log.info("gan_demo_mode_no_model_load")
            return

        try:
            self.generator = Generator()
            if os.path.exists(self.checkpoint_path):
                state = torch.load(self.checkpoint_path, map_location="cpu")
                self.generator.load_state_dict(state)
                self.generator.eval()
                log.info("gan_generator_loaded", path=self.checkpoint_path)
            else:
                log.warning("gan_checkpoint_not_found", path=self.checkpoint_path)
                self.generator = None
        except Exception as e:
            log.warning("gan_load_failed", error=str(e))
            self.generator = None

    def generate(
        self,
        n_samples: int = 10,
        basin_id: str = "brahmaputra_upper",
        season: str = "monsoon",
        severity: float = 0.7,
    ) -> Dict[str, Any]:
        """Generate synthetic flood sequences.

        Returns dict with:
          - data: np.ndarray of shape (n_samples, n_features, seq_len)
          - features: list of feature names
          - metadata: generation parameters
        """
        if DEMO_MODE or self.generator is None:
            return self._demo_generate(n_samples, basin_id, season, severity)

        return self._gan_generate(n_samples, basin_id, season, severity)

    def _demo_generate(
        self, n_samples: int, basin_id: str, season: str, severity: float
    ) -> Dict[str, Any]:
        """Generate using deterministic NumPy patterns."""
        sequences = []
        for i in range(n_samples):
            seq = _generate_demo_sequence(
                severity=severity + np.random.uniform(-0.1, 0.1),
                season=season,
                steps=48,
            )
            sequences.append(seq)

        data = np.stack(sequences)  # (n_samples, n_features, 48)

        return {
            "data": data.tolist(),
            "shape": list(data.shape),
            "features": FEATURE_NAMES,
            "metadata": {
                "n_samples": n_samples,
                "basin_id": basin_id,
                "season": season,
                "severity": severity,
                "method": "numpy_demo",
                "generated_at": datetime.utcnow().isoformat(),
            },
        }

    def _gan_generate(
        self, n_samples: int, basin_id: str, season: str, severity: float
    ) -> Dict[str, Any]:
        """Generate using trained DCGAN."""
        import torch

        z = torch.randn(n_samples, 100)

        # Build condition vector
        basin_idx = BASIN_IDS.index(basin_id) if basin_id in BASIN_IDS else 0
        season_idx = SEASONS.index(season) if season in SEASONS else 0
        cond = torch.zeros(n_samples, 8)
        cond[:, basin_idx] = 1.0          # one-hot basin
        cond[:, 4 + season_idx] = 1.0     # one-hot season (offset by 4)
        # Could embed severity as well

        with torch.no_grad():
            generated = self.generator(z, cond)

        data = generated.cpu().numpy()

        return {
            "data": data.tolist(),
            "shape": list(data.shape),
            "features": FEATURE_NAMES,
            "metadata": {
                "n_samples": n_samples,
                "basin_id": basin_id,
                "season": season,
                "severity": severity,
                "method": "conditional_dcgan",
                "generated_at": datetime.utcnow().isoformat(),
            },
        }
