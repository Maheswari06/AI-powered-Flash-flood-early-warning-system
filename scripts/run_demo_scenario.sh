#!/bin/bash
# ══════════════════════════════════════════════════════════════
# ARGUS — 7-Minute Demo Scenario Runner
# Triggers all demo moments in sequence for the hackathon pitch
# ══════════════════════════════════════════════════════════════

set -e

GATEWAY="http://localhost:8000"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

demo_step() {
    local step=$1
    local title=$2
    echo ""
    echo -e "${BOLD}${CYAN}═══ Demo Moment $step: $title ═══${NC}"
}

hit() {
    local method=$1
    local url=$2
    local data=$3
    if [ "$method" = "POST" ] && [ -n "$data" ]; then
        resp=$(curl -s -w "\n%{http_code}" -X POST "$url" -H "Content-Type: application/json" -d "$data" 2>/dev/null)
    elif [ "$method" = "POST" ]; then
        resp=$(curl -s -w "\n%{http_code}" -X POST "$url" 2>/dev/null)
    else
        resp=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null)
    fi
    code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')
    if [ "$code" = "200" ]; then
        echo -e "  ${GREEN}✅ $url → $code${NC}"
        echo "$body" | python3 -m json.tool 2>/dev/null | head -20 || echo "$body" | head -5
    else
        echo -e "  ${YELLOW}⚠️  $url → $code${NC}"
    fi
}

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🌊 ARGUS — 7-Minute Demo Scenario"
echo "  Triggering all demo moments in sequence..."
echo "════════════════════════════════════════════════════════"

# ── Pre-flight: Health Check ─────────────────────────────
echo -e "\n${BOLD}Pre-flight health check...${NC}"
hit GET "$GATEWAY/health"
sleep 1

# ── Moment 1: CV Virtual Gauging ─────────────────────────
demo_step 1 "CV Virtual Gauging — Camera sees flood depth"
hit GET "http://localhost:8002/api/v1/virtual-gauge/bridge_beas_01/latest"
sleep 2

# ── Moment 2: Causal Intervention ────────────────────────
demo_step 2 "Causal Engine — What-if dam gate scenario"
hit POST "http://localhost:8007/api/v1/causal/intervene" '{"basin_id":"brahmaputra_upper","intervention":{"variable":"dam_pandoh_gate","value":0.25,"unit":"fraction_open"},"target_variable":"downstream_flood_depth"}'
sleep 2

# ── Moment 3: CHORUS Community Intelligence ─────────────
demo_step 3 "CHORUS — WhatsApp community sensing"
hit POST "http://localhost:8008/api/v1/chorus/demo" '{"text":"नदी बहुत तेज़ बह रही है","location":"majuli_bridge"}'
sleep 2

# ── Moment 4: Prediction + SHAP ─────────────────────────
demo_step 4 "Prediction — SHAP explainability"
hit GET "http://localhost:8004/api/v1/predictions/all"
sleep 2

# ── Moment 5: Evacuation Choreography ───────────────────
demo_step 5 "Evacuation RL — Multi-agent rescue plan"
hit POST "http://localhost:8011/api/v1/evacuation/demo"
sleep 2

# ── Moment 6: FloodLedger Blockchain ───────────────────
demo_step 6 "FloodLedger — Parametric insurance payout"
hit POST "http://localhost:8010/api/v1/ledger/demo-trigger"
sleep 2

# ── Moment 7: ScarNet Terrain Detection ─────────────────
demo_step 7 "ScarNet — Satellite terrain change detection"
hit POST "http://localhost:8013/api/v1/scarnet/trigger-demo"
sleep 2

# ── Moment 8: MIRROR Counterfactual ────────────────────
demo_step 8 "MIRROR — Counterfactual replay"
hit POST "http://localhost:8012/api/v1/mirror/demo"
sleep 1

# ── Moment 9: System Health ─────────────────────────────
demo_step 9 "Full System Health — All services green"
hit GET "$GATEWAY/health"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  🎯 Demo scenario complete!"
echo "  Dashboard: http://localhost:5173"
echo "════════════════════════════════════════════════════════"
echo ""
