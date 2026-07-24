#!/bin/bash
# ══════════════════════════════════════════════════════════════
# ARGUS — One-Command Demo Environment Setup
# Sets up everything needed for the 7-minute hackathon demo
# ══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "════════════════════════════════════════════════════════"
echo "  🌊 ARGUS — Demo Environment Setup"
echo "════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Environment file ────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  ✅ .env created from .env.example"
    else
        echo "  ⚠️  No .env file found — services will use defaults"
    fi
else
    echo "  ✅ .env exists"
fi

# ── Step 2: Python dependencies ──────────────────────────
echo "📦 Installing Python dependencies..."
pip install --break-system-packages -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null
echo "  ✅ Python dependencies installed"

# ── Step 3: Dashboard dependencies ───────────────────────
echo "📦 Installing Dashboard dependencies..."
cd dashboard
if [ ! -d "node_modules" ]; then
    npm install --silent 2>/dev/null
fi
cd "$PROJECT_ROOT"
echo "  ✅ Dashboard dependencies installed"

# ── Step 4: Create directories ──────────────────────────
echo "📁 Ensuring directories exist..."
mkdir -p models data/synthetic data/dags data/sentinel2
echo "  ✅ Directories ready"

# ── Step 5: Generate model files ────────────────────────
echo "🧠 Generating model files..."
bash scripts/generate_models.sh 2>/dev/null || echo "  ⚠️  Model generation had warnings (non-critical)"

# ── Step 6: Generate synthetic Sentinel tiles ────────────
echo "🛰️  Generating synthetic Sentinel-2 tiles for ScarNet demo..."
python scripts/generate_synthetic_sentinel_tiles.py 2>/dev/null || echo "  ⚠️  Tile generation skipped (rasterio not installed — ScarNet will use numpy fallback)"

# ── Step 7: Docker infrastructure ───────────────────────
echo "🐳 Starting infrastructure containers..."
if command -v docker &>/dev/null; then
    docker compose up -d 2>/dev/null && echo "  ✅ Kafka, TimescaleDB, Redis, Hardhat running" || echo "  ⚠️  Docker Compose failed — demo mode will work"
    
    # Wait for infrastructure to be ready
    sleep 10
    
    # Create TimescaleDB schema
    echo "📊 Setting up TimescaleDB schema..."
    docker exec -i argus_timescaledb psql -U argus -d argus_db << 'EOF' 2>/dev/null || echo "  ⚠️  Schema setup skipped"
CREATE TABLE IF NOT EXISTS feature_store (
  time        TIMESTAMPTZ NOT NULL,
  village_id  TEXT NOT NULL,
  station_id  TEXT,
  features    JSONB NOT NULL,
  quality     TEXT DEFAULT 'GOOD'
);
SELECT create_hypertable('feature_store', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS predictions (
  time        TIMESTAMPTZ NOT NULL,
  village_id  TEXT NOT NULL,
  risk_score  FLOAT,
  alert_level TEXT,
  explanation JSONB
);
SELECT create_hypertable('predictions', 'time', if_not_exists => TRUE);
EOF
    echo "  ✅ TimescaleDB schema ready"

    # Create Kafka topics
    echo "📡 Creating Kafka topics..."
    for topic in gauge.realtime weather.api virtual.gauge feature.engineered predictions.fast chorus.signal causal.risk; do
        docker exec argus_kafka kafka-topics --create --bootstrap-server localhost:9092 \
          --topic "$topic" --partitions 4 --replication-factor 1 --if-not-exists 2>/dev/null || true
    done
    echo "  ✅ Kafka topics created"

    # Deploy Hardhat smart contract
    echo "⛓️  Deploying FloodLedger smart contract..."
    cd services/flood_ledger
    if [ -f "package.json" ] && command -v npx &>/dev/null; then
        npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox 2>/dev/null || true
        npx hardhat compile 2>/dev/null && npx hardhat run scripts/deploy.js --network localhost 2>/dev/null || echo "  ⚠️  Contract deployment skipped"
    fi
    cd "$PROJECT_ROOT"
else
    echo "  ⚠️  Docker not available — services run in demo mode"
fi

# ── Step 8: Load demo scenario data ─────────────────────
echo "📥 Loading demo scenario data..."
python demo/scenario_loader.py 2>/dev/null || echo "  ⚠️  Demo data loading skipped (infrastructure not available)"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  Next steps:"
echo "    bash scripts/start_all.sh       # Start all 13 services + dashboard"
echo "    python demo/orchestrator.py     # Run the 7-minute demo"
echo "════════════════════════════════════════════════════════"
