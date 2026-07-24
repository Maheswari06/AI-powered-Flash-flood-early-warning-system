# ARGUS — Demo Video Script
## 3-Minute Screen Recording Script
### Prepared by Dhana | Backup if live demo fails + post-event judge viewing

---

## Recording Setup

- **Resolution:** 1920×1080 minimum, 2560×1440 preferred
- **FPS:** 30
- **Audio:** Rogesh narrates (clear, steady pace)
- **Software:** OBS Studio or built-in screen recorder
- **Browser:** Chrome, dark mode, zoom 110%
- **Dashboard URL:** `http://localhost:5173`

### Pre-Recording Checklist

- [ ] All 12 services running (`docker-compose ps`)
- [ ] Health checker passing (`python demo/health_checker.py`)
- [ ] Orchestrator loaded (`python demo/orchestrator.py`)
- [ ] Dashboard open with Majuli Ward 7 selected
- [ ] Browser tab: Dashboard → Causal → Evacuation → FloodLedger → MIRROR
- [ ] Terminal visible in bottom-right (small, for API calls)
- [ ] Mouse cursor: large, visible on dark background

---

## Script

### [00:00–00:10] Opening

*[Screen: ARGUS dashboard, dark theme, Deck.gl map centered on Assam]*

**Narration:** "This is ARGUS — an AI system that detects floods before sensors can, prescribes specific interventions, and delivers warnings even when the internet is down."

---

### [00:10–00:40] The Eyes — CV Gauging + PINN

*[Click on a camera icon on the map → CV Gauging panel opens]*

**Narration:** "ARGUS converts existing CCTV cameras into calibrated flood instruments."

*[YOLO overlay appears, SAM2 water mask paints cyan]*

**Narration:** "YOLO v11 detects the water surface. SAM 2 segments it. Geometric calibration gives us depth and velocity — from a traffic camera."

*[Toggle to PINN mesh view → 5,000 dots appear across the basin]*

**Narration:** "Where there are no cameras, our Physics-Informed Neural Network interpolates — 5,000 virtual sensors across the basin, constrained by the laws of fluid dynamics."

---

### [00:40–01:10] The Brain — Prediction + Causal Intervention

*[Click on Majuli Ward 7 → Risk panel opens. Risk score: 0.91, EMERGENCY]*

**Narration:** "Risk score: 0.91 — emergency. And here's why."

*[SHAP explanation panel: three factors listed]*

**Narration:** "Water velocity contributing 44%. Soil saturation 38%. Upstream surge 18%. Every prediction is fully explained."

*[Switch to Causal Intervention tab → Type: "Open Pandoh Dam Gate 2 to 25%" → Click Compute]*

**Narration:** "But ARGUS doesn't just predict. It prescribes."

*[Result: Baseline 4.7m → Intervened 3.1m. Damage reduction 34%]*

**Narration:** "Open this specific dam gate to this specific level — and reduce flood damage by 34%. This is causal inference, not just correlation. No other flood system in the world does this."

---

### [01:10–01:40] The Voice — Offline Resilience

*[Show ACN status panel: CLOUD MODE]*

**Narration:** "Now watch what happens when the internet dies."

*[Toggle the "Simulate Offline" switch → Status changes: OFFLINE — ORACLE ACTIVE]*

**Narration:** "The Autonomous Crisis Node — a five-thousand rupee Raspberry Pi — just switched to its local AI model."

*[LoRaWAN siren widget activates]*

**Narration:** "LoRaWAN sirens activated. No internet required. Range: 20 kilometers."

*[Phone notification animation]*

**Narration:** "And an audio evacuation instruction — in Assamese — just reached 3,847 people via voice call. The flood cannot silence ARGUS."

---

### [01:40–02:10] The Plan — RL Evacuation

*[Switch to Evacuation tab → Majuli Ward 7 map with route lines]*

**Narration:** "ARGUS doesn't just warn. It plans the rescue."

*[Zoom to see bus assignment: AS-01-CD-8872, route via NH-715]*

**Narration:** "2,340 people. Bus assigned. Route selected — avoiding the road that floods in 67 minutes. Shelter at Jorhat Community Hall, capacity 400."

*[Show WhatsApp notification → NDRF webhook → Traffic signal override]*

**Narration:** "WhatsApp audio to the Sarpanch. NDRF dispatched. Traffic signals overridden. Every person has a seat, a route, and a shelter."

---

### [02:10–02:40] The Money — FloodLedger

*[Switch to FloodLedger tab → Map with insured assets]*

**Narration:** "When the satellite confirms the flood..."

*[Click "Simulate Flood Event" → Smart contract fires]*

**Narration:** "...the smart contract self-executes. Payout: fourteen lakh seventy thousand rupees. No claims adjuster. No six-month wait. The tea estate owner is compensated within 24 hours."

---

### [02:40–03:00] The Close

*[Switch to MIRROR tab → Backtest timeline]*

**Narration:** "August 14, 2023. Himachal Pradesh. Official warning: T minus 8 minutes. ARGUS: T minus 78 minutes. 70 minutes of additional warning. 40 to 47 lives that could have been saved."

*[Pause on the timeline visualization]*

**Narration:** "Every flood system tells you a flood is coming. ARGUS tells you what to do about it."

*[Fade to ARGUS logo on dark background]*

---

## Post-Production Notes

1. Add subtle background music (low, ambient — not distracting)
2. Add text overlays for key numbers: "78 min lead time", "34% damage reduction", "40–47 lives"
3. Export as MP4, H.264, 1080p minimum
4. Upload to both YouTube (unlisted) and Google Drive
5. Test playback on the presentation laptop before the event

## File Naming

```
ARGUS_Demo_v1_YYYYMMDD.mp4
```

## Duration Target

| Section | Target | Max |
|---------|--------|-----|
| Opening | 10s | 12s |
| CV + PINN | 30s | 35s |
| Prediction + Causal | 30s | 35s |
| Offline | 30s | 35s |
| Evacuation | 30s | 35s |
| FloodLedger | 30s | 35s |
| Close | 20s | 25s |
| **Total** | **2:40** | **3:00** |
