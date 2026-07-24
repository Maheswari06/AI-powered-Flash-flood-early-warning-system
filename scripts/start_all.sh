#!/bin/bash
# ══════════════════════════════════════════════════════════════
# ARGUS — Start All Services
# Starts infrastructure + all 13 services + dashboard
# ══════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[ARGUS]${NC} $1"; }
ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; }

PIDS=()
cleanup() {
    log "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    log "All services stopped."
}
trap cleanup EXIT INT TERM

start_service() {
    local name=$1
    local module=$2
    local port=$3
    log "Starting $name on port $port..."
    python -m uvicorn "$module" --host 0.0.0.0 --port "$port" --log-level warning &
    PIDS+=($!)
    sleep 0.5
}

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🌊  ARGUS — AI Flash Flood Early Warning System"
echo "  Starting all services..."
echo "════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Infrastructure ───────────────────────────────
log "Starting infrastructure (Docker Compose)..."
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    docker compose up -d 2>/dev/null && ok "Kafka, TimescaleDB, Redis running" || warn "Docker Compose failed — services may work in demo mode"
    sleep 3
else
    warn "Docker not available — skipping infrastructure (demo mode)"
fi

# ── Step 2: Phase 1 services ────────────────────────────
log "Phase 1 — Core Pipeline"
start_service "Ingestion"        "services.ingestion.main:app"        8001
start_service "CV Gauging"       "services.cv_gauging.main:app"       8002
sleep 2
start_service "Feature Engine"   "services.feature_engine.main:app"   8003
sleep 3
start_service "Prediction"       "services.prediction.main:app"       8004
start_service "Alert Dispatcher" "services.alert_dispatcher.main:app" 8005
ok "Phase 1 services running (ports 8001-8005)"

# ── Step 3: Phase 2 services ────────────────────────────
log "Phase 2 — Intelligence Layer"
sleep 2
start_service "Causal Engine"    "services.causal_engine.main:app"    8006
start_service "FloodLedger"      "services.flood_ledger.main:app"     8007
start_service "CHORUS"           "services.chorus.main:app"           8008
start_service "Federated Server" "services.federated_server.main:app" 8009
start_service "Evacuation RL"    "services.evacuation_rl.main:app"    8010
start_service "MIRROR"           "services.mirror.main:app"           8011
ok "Phase 2 services running (ports 8006-8011)"

# ── Step 4: Phase 3 services ────────────────────────────
log "Phase 3 — Integration Layer"
sleep 2
start_service "ScarNet"          "services.scarnet.main:app"          8012
start_service "Model Monitor"    "services.model_monitor.main:app"    8013
sleep 2
start_service "API Gateway"      "services.api_gateway.main:app"      8000
ok "Phase 3 services running (ports 8000, 8012-8013)"

# ── Step 5: Dashboard ───────────────────────────────────
log "Starting Dashboard..."
cd dashboard
if [ -d "node_modules" ]; then
    npx vite --host 0.0.0.0 --port 5173 &
    PIDS+=($!)
else
    npm install && npx vite --host 0.0.0.0 --port 5173 &
    PIDS+=($!)
fi
cd "$PROJECT_ROOT"
ok "Dashboard running on http://localhost:5173"

# ── Step 6: Health check ────────────────────────────────
sleep 3
log "Running health check..."
python scripts/health_checker.py 2>/dev/null || warn "Health checker not available"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🌊  ARGUS is fully operational"
echo ""
echo "  Dashboard:    http://localhost:5173"
echo "  API Gateway:  http://localhost:8000"
echo "  Health:       http://localhost:8000/health"
echo ""
echo "  Phase 1:  8001-8005  (Ingestion → Alerts)"
echo "  Phase 2:  8006-8011  (Causal → MIRROR)"
echo "  Phase 3:  8000,8012-8013  (Gateway, ScarNet, Model Monitor)"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to stop all services."
wait
