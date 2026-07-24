#!/bin/bash
set -e
LOG_DIR="logs"
mkdir -p $LOG_DIR

echo "🌊 Starting ARGUS Backend Services..."
echo ""

# Helper: start a service with logging
start_svc() {
    local name=$1
    local module=$2
    local port=$3
    local log="$LOG_DIR/${name}.log"

    # Kill if already running on this port
    lsof -ti:$port | xargs kill -9 2>/dev/null || true
    sleep 0.5

    echo -n "  Starting $name (port $port)... "
    DEMO_MODE=true python3 -m uvicorn $module \
        --port $port \
        --host 0.0.0.0 \
        --log-level warning \
        > "$log" 2>&1 &

    PID=$!
    sleep 2

    # Quick health check
    if kill -0 $PID 2>/dev/null; then
        echo "✅ (PID $PID)"
    else
        echo "❌ FAILED — check $log"
        tail -5 "$log"
    fi
}

# ─── Phase 1 Services ────────────────────────────────────────
echo "── Phase 1 ──────────────────────────────"
start_svc "ingestion"         "services.ingestion.main:app"         8001
start_svc "cv_gauging"        "services.cv_gauging.main:app"        8002
sleep 1
start_svc "feature_engine"    "services.feature_engine.main:app"    8003
sleep 1
start_svc "prediction"        "services.prediction.main:app"        8004
start_svc "alert_dispatcher"  "services.alert_dispatcher.main:app"  8005

# ─── Phase 2 Services ────────────────────────────────────────
echo ""
echo "── Phase 2 ──────────────────────────────"
sleep 1
start_svc "causal_engine"     "services.causal_engine.main:app"     8006
start_svc "flood_ledger"      "services.flood_ledger.main:app"      8007
start_svc "chorus"            "services.chorus.main:app"            8008
start_svc "federated_server"  "services.federated_server.main:app"  8009
start_svc "evacuation_rl"     "services.evacuation_rl.main:app"     8010
start_svc "mirror"            "services.mirror.main:app"            8011

# ─── Phase 3 Services ────────────────────────────────────────
echo ""
echo "── Phase 3 ──────────────────────────────"
sleep 1
start_svc "scarnet"           "services.scarnet.main:app"           8012
start_svc "model_monitor"     "services.model_monitor.main:app"     8013

# ─── Phase 5 Services ────────────────────────────────────────
echo ""
echo "── Phase 5/6 ───────────────────────────"
sleep 1
start_svc "notification_hub"  "services.notification_hub.main:app"  8014
start_svc "multi_basin"       "services.multi_basin.main:app"       8015
start_svc "copilot"           "services.copilot.main:app"           8016

# ─── API Gateway LAST (depends on all others) ─────────────────
echo ""
echo "── API Gateway ─────────────────────────"
sleep 2
start_svc "api_gateway"       "services.api_gateway.main:app"       8000

echo ""
echo "════════════════════════════════════════"
echo "✅ All backend services launched"
echo "   Logs: $LOG_DIR/"
echo "════════════════════════════════════════"
