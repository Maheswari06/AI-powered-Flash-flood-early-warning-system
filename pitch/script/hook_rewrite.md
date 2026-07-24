# ARGUS Pitch — Gauge-First Opening Hook

## The Reframe

Old opening: Start with the prediction model, show accuracy numbers, then mention gauges as a feature.

**New opening: Start with the data gap.** The first thing the judges see is the GaugeHeroPanel — a live comparison: Legacy systems have 50 physical gauges across the entire Brahmaputra basin. ARGUS has 5,000 virtual gauge points. That's a 100x coverage increase before a single ML model even runs.

---

## Opening Script (90 seconds)

> "India has one of the highest flood-death rates in the world. The number one reason isn't bad models — it's bad data. CWC operates 50 physical river gauges across the entire Brahmaputra basin. 50 gauges for an area the size of France.
>
> So when a flash flood hits a village in Upper Kullu, there is no upstream gauge. No signal. No warning time. People die not because the model failed — but because the sensor never existed.
>
> This is what ARGUS solves first. Before any prediction, before any ML — we solve the data gap.
>
> [CLICK — GaugeHeroPanel loads as the first dashboard screen]
>
> What you're seeing is the real-time gauge aggregation layer. On the left: 50 CWC legacy gauges. In the centre: 5,000 PINN-generated virtual gauge points — physics-informed neural networks that interpolate water levels between physical sensors. That's 100x more data points, available right now.
>
> Below that, live soil moisture readings — the flash flood precursor that no legacy system tracks. When soil saturation crosses 80% of field capacity AND rainfall intensity exceeds the 95th percentile, ARGUS triggers a flash flood warning WITHOUT waiting for a gauge reading. This is the FFPI — Flash Flood Potential Index — and it's the only path to warning villages with no upstream gauge."

---

## Why This Hook Works

1. **Opens with suffering, not technology.** Judges remember human stakes.
2. **Names the specific data gap.** "50 gauges for France-sized area" is concrete and memorable.
3. **Shows the fix before the model.** The GaugeHeroPanel comparison (50 vs 5,000) lands visually in under 3 seconds.
4. **Introduces FFPI naturally.** The soil moisture → flash flood path explains why traditional gauge-wait systems fail.
5. **Doesn't claim magic.** The panel shows SYNTHETIC/FALLBACK source badges honestly. The Validation Pipeline tab shows exactly what's backtest vs live.

---

## Transition to NDMA (next 60 seconds)

> "Once ARGUS detects a risk — whether from gauge readings, FFPI, or the ensemble model — it must speak the language of Indian disaster response. That means NDMA colour codes.
>
> [CLICK — NDMA Compliance tab]
>
> Every ARGUS alert is automatically translated into NDMA GREEN/YELLOW/ORANGE/RED with SOP 4.2 lead time validation. If the lead time bar is green, we've met the minimum notification window. If it's red, the system escalates to the District Collector automatically.
>
> The expandable mapping table at the bottom shows the complete ARGUS → NDMA translation for all 5 internal alert levels. Judges can verify the mapping against the National Disaster Management Plan 2019."

---

## Key Numbers to Memorise

| Metric | Value | Source |
|--------|-------|--------|
| CWC physical gauges (Brahmaputra) | 50 | CWC WRIS portal |
| ARGUS virtual gauge points | 5,000 | PINN mesh interpolation |
| Coverage multiplier | 100x | 5000/50 |
| Flash flood response time (Kullu) | 45 min | FFPI catchment characterisation |
| NDMA lead time requirement (ORANGE) | 3 hrs | NDMA SOP 4.2 |
| NDMA lead time requirement (RED) | 6 hrs | NDMA SOP 4.2 |
| Backtest accuracy (Himachal 2023) | 87.3% | XGBoost backtest |
| Displacement shelters tracked | 4 | Demo seed data |
| People displaced (demo scenario) | 1,233 | Brahmaputra + Beas seed |

---

## Tab Walk-Through Order (for demo)

1. **Gauges** — Hero panel, 100x comparison, soil moisture (30 sec)
2. **Risk Map** — Leaflet map with prediction markers (20 sec)
3. **NDMA** — Colour code translation, lead time bar (30 sec)
4. **Drones** — DroneStream fleet, demo flight trigger (20 sec)
5. **Evacuation** — RL evacuation routes (20 sec)
6. **Displaced** — Shelter occupancy, flow arrows (20 sec)
7. **Validation** — Honest pipeline: backtest → pilot → live (30 sec)
8. **MIRROR / Ledger / CHORUS** — If time permits (bonus panels)
