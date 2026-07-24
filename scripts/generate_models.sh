#!/bin/bash
# ══════════════════════════════════════════════════════════════
# ARGUS — Generate / Download All Model Files
# Creates stubs + trains XGBoost from synthetic data
# ══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "🧠 Generating ARGUS model files..."

mkdir -p models data/synthetic data/dags data/sentinel2

# ── 1. Download YOLO v11 nano (6MB) ──────────────────────
echo "📦 Downloading YOLO v11n..."
python -c "
try:
    from ultralytics import YOLO
    YOLO('yolo11n.pt')
    import shutil; shutil.move('yolo11n.pt', 'models/yolo11n.pt')
    print('  ✅ YOLO v11n downloaded')
except ImportError:
    print('  ⚠️  ultralytics not installed — skipping YOLO download')
except Exception as e:
    print(f'  ⚠️  YOLO download failed: {e}')
"

# ── 2. Train XGBoost from synthetic data (~3 min) ────────
echo "📦 Training XGBoost flood classifier..."
python - << 'PYEOF'
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
import joblib

np.random.seed(42)
n = 10000

X = pd.DataFrame({
    'level_1hr_mean': np.random.uniform(0.5, 8.0, n),
    'level_3hr_mean': np.random.uniform(0.5, 8.0, n),
    'level_6hr_mean': np.random.uniform(0.5, 8.0, n),
    'level_24hr_mean': np.random.uniform(0.5, 8.0, n),
    'level_1hr_max': np.random.uniform(0.5, 10.0, n),
    'rate_of_change_1hr': np.random.uniform(-0.5, 2.0, n),
    'rate_of_change_3hr': np.random.uniform(-0.5, 1.5, n),
    'cumulative_rainfall_6hr': np.random.uniform(0, 150, n),
    'cumulative_rainfall_24hr': np.random.uniform(0, 400, n),
    'soil_moisture_index': np.random.uniform(0, 1, n),
    'antecedent_moisture_index': np.random.uniform(0, 1, n),
    'upstream_risk_score': np.random.uniform(0, 1, n),
    'basin_connectivity_score': np.random.uniform(0, 1, n),
    'hour_of_day': np.random.randint(0, 24, n),
    'day_of_year': np.random.randint(1, 366, n),
    'is_monsoon_season': np.random.randint(0, 2, n),
})

y = (
    (X['level_6hr_mean'] > 4.5) &
    (X['cumulative_rainfall_6hr'] > 60) &
    (X['soil_moisture_index'] > 0.6)
).astype(int)

model = XGBClassifier(n_estimators=500, max_depth=6, learning_rate=0.05,
                      subsample=0.8, use_label_encoder=False, eval_metric='logloss')
model.fit(X, y)
joblib.dump(model, 'models/xgboost_flood.joblib')
print(f"  ✅ XGBoost trained — flood rate: {y.mean():.1%}")
PYEOF

# ── 3. Create PINN stub model ────────────────────────────
echo "📦 Creating PINN stub..."
python - << 'PYEOF'
import torch, torch.nn as nn

class PINNStub(nn.Module):
    """Must match SaintVenantPINN in services/feature_engine/pinn_mesh.py"""
    def __init__(self, hidden=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(2, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 1),
        )
    def forward(self, x): return self.net(x)

torch.save(PINNStub().state_dict(), 'models/pinn_beas_river.pt')
torch.save(PINNStub().state_dict(), 'models/pinn_brahmaputra.pt')
print("  ✅ PINN stubs saved (beas_river + brahmaputra)")
PYEOF

# ── 4. Create Causal GNN stub model ─────────────────────
echo "📦 Creating Causal GNN stub..."
python - << 'PYEOF'
import torch, torch.nn as nn

class CausalGNNStub(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(5, 1)
    def forward(self, x): return torch.sigmoid(self.fc(x))

torch.save(CausalGNNStub().state_dict(), 'models/causal_gnn_brahmaputra.pt')
print("  ✅ Causal GNN stub saved")
PYEOF

# ── 5. Create ORACLE TinyML stubs ────────────────────────
echo "📦 Creating ORACLE models..."
python - << 'PYEOF'
import joblib, numpy as np
from xgboost import XGBClassifier

for name, threshold in [("majuli", 3.5), ("himachal", 4.0)]:
    np.random.seed(42)
    X = np.random.rand(500, 6)
    y = (X[:, 0] > threshold/10 + 0.3).astype(int)
    m = XGBClassifier(n_estimators=50, max_depth=3)
    m.fit(X, y)
    joblib.dump(m, f'models/oracle_{name}.joblib')
    print(f"  ✅ ORACLE {name} model saved")
PYEOF

# ── 6. Create synthetic Sentinel-2 tiles ─────────────────
echo "🛰️  Creating synthetic Sentinel-2 tiles..."
python - << 'PYEOF'
try:
    import numpy as np, rasterio
    from rasterio.transform import from_bounds

    def make_fake_sentinel2(path, ndvi_mean, seed=0):
        np.random.seed(seed)
        transform = from_bounds(77.0, 31.4, 77.2, 31.6, 100, 100)
        with rasterio.open(path, 'w', driver='GTiff', height=100, width=100,
                           count=13, dtype='float32', crs='EPSG:4326',
                           transform=transform) as dst:
            for band in range(1, 14):
                data = np.random.rand(100, 100).astype('float32')
                if band == 4: data = data * 0.3
                if band == 8: data = (data * 0.3 + ndvi_mean).clip(0,1)
                dst.write(data, band)

    import os
    os.makedirs('data/sentinel2', exist_ok=True)
    make_fake_sentinel2('data/sentinel2/beas_valley_2022_08_before.tif', 0.6, seed=1)
    make_fake_sentinel2('data/sentinel2/beas_valley_2023_09_after.tif', 0.25, seed=2)
    print("  ✅ Synthetic Sentinel-2 tiles created")
except ImportError:
    print("  ⚠️  rasterio not installed — ScarNet will use numpy fallback")
    import numpy as np, os
    os.makedirs('data/sentinel2', exist_ok=True)
    np.save('data/sentinel2/beas_valley_before.npy', np.random.rand(100,100,13).astype('float32'))
    np.save('data/sentinel2/beas_valley_after.npy', np.random.rand(100,100,13).astype('float32'))
    print("  ✅ Numpy fallback tiles created")
PYEOF

echo ""
echo "✅ All model files ready"
ls -lh models/
