# ARGUS — Pitch Timing Guide
## 7-Minute Presentation Timer

| Slide # | Segment | Speaker | Start | End | Target | Hard Max | Notes |
|---------|---------|---------|-------|-----|--------|----------|-------|
| 1 | **HOOK** — Water pour + sensor death | Rogesh | 0:00 | 1:30 | 90s | 100s | Props: glass, muddy water, marker |
| 2 | **THE EYES** — CV Gauging + SHAP | Dhana (slides) | 1:30 | 2:30 | 55s | 70s | Live CCTV overlay demo |
| 3 | **THE BRAIN** — Causal Intervention | Rogesh | 2:30 | 3:45 | 70s | 80s | Type intervention query live |
| 4 | **THE VOICE** — WiFi Kill + ACN | Dhana (props) | 3:45 | 4:45 | 55s | 65s | Unplug WiFi, phone rings |
| 5 | **THE PLAN** — RL Evacuation | Sabarish | 4:45 | 5:45 | 55s | 65s | Zoom to Majuli Ward 7 |
| 6 | **THE MONEY** — FloodLedger | Sabarish | 5:45 | 6:30 | 45s | 55s | Smart contract fires |
| 7 | **THE CLOSE** — Backtest Timeline | Rogesh | 6:30 | 7:00 | 30s | 35s | Silence at end |
| | **TOTAL** | | 0:00 | 7:00 | **6:40** | **7:30** | |

---

## Checkpoints During Rehearsal

| Checkpoint | Time | Action if Behind |
|-----------|------|-----------------|
| Water pour complete | 0:45 | Skip second CWC detail sentence |
| ARGUS logo on screen | 1:30 | If > 1:40, cut SHAP to 1 factor |
| Intervention result appears | 3:30 | If > 3:50, skip "No other flood system" line |
| WiFi reconnected | 4:40 | If > 4:50, skip shelter occupancy detail |
| Smart contract fires | 6:20 | If > 6:30, go straight to closing line |
| Final silence begins | 6:50 | Hold 5 seconds, no matter what |

---

## Speaker Handoff Cues

| From | To | Cue Line | Action |
|------|-----|---------|--------|
| Rogesh | Dhana | "...sees more than all of them combined." | Dhana advances to CCTV slide |
| Dhana | Rogesh | "...a District Collector can act on at two in the morning." | Rogesh steps forward |
| Rogesh | Dhana | "No other flood system in the world does this." | Dhana reaches for WiFi cable |
| Dhana | Sabarish | "ARGUS cannot be blinded." | Sabarish takes laptop control |
| Sabarish | Rogesh | "...saves them more than it costs." | Rogesh steps to center |

---

## Emergency Protocols

| Scenario | Response |
|----------|----------|
| Demo crashes | Dhana switches to backup video within 3 seconds |
| Timer hits 6:30 and still on Minute 5 | Skip FloodLedger, go directly to closing |
| Judge interrupts with question | Answer in 1 sentence, "I'll cover that in a moment" |
| Props fail (water spills) | Skip prop, use verbal description instead |
| Audio/IVR doesn't play | Rogesh describes what would play, Dhana troubleshoots |

---

## Pre-Show Countdown (T-15 minutes)

- [ ] T-15: `docker-compose ps` — all 12 services UP
- [ ] T-12: `python demo/health_checker.py` — all green
- [ ] T-10: `python demo/orchestrator.py` — scenario loaded
- [ ] T-8: Dashboard open, all tabs verified
- [ ] T-5: Props positioned (glass, water, marker, WiFi cable)
- [ ] T-3: Backup video queued on phone
- [ ] T-2: Deep breath. Look at teammates. Nod.
- [ ] T-0: **"This gauge costs three lakh rupees."**
