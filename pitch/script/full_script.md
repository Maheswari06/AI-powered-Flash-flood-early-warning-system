# ARGUS — 7-Minute Pitch Script
## Word-for-Word with Timing Marks

**Team Assignment:**
- **Rogesh:** Presents Minutes 1, 3, and 7
- **Sabarish:** Controls the demo laptop. Run `orchestrator.py` beforehand.
- **Dhana:** Manages physical props (water glass, marker) and backup phone. Advances slides.

**Pre-show Checklist:**
- [ ] Glass of clear water on table
- [ ] CWC sensor photograph printed
- [ ] Muddy water + pebbles in container
- [ ] Red marker at hand
- [ ] WiFi cable accessible and pluggable
- [ ] Backup phone with Twilio IVR ready
- [ ] `python demo/orchestrator.py` running on demo laptop
- [ ] Dashboard open at `http://localhost:5173`

---

### [00:00–01:30] MINUTE 1 — THE HOOK (Rogesh presents)

*[Place the glass of clear water on the table. Hold up the CWC sensor photograph.]*

"This gauge costs three lakh rupees."

*[Pause. Let them look at it.]*

"It measures water depth with millimeter precision. It transmits every fifteen seconds. It is the gold standard of Indian flood monitoring."

*[Slowly pour muddy water and a handful of pebbles into the glass. The water turns opaque.]*

"And this — is what happens when the flood it was supposed to detect finally arrives."

*[Draw a red X through the sensor with a marker.]*

"The debris wall that precedes every flash flood destroys the sensor before the sensor can send a single alert. Right now, across India, five thousand sensors are offline. Not because of budget cuts. Because the disaster came first."

*[Click to next slide — ARGUS logo appears.]*

"ARGUS does not have a single sensor."

*[Pause.]*

"And it sees more than all of them combined."

---

### [01:30–02:30] MINUTE 2 — THE EYES (Dhana advances slides)

*[Slide: Live CCTV feed from bridge camera. YOLO overlay appears.]*

"This is a standard traffic camera. Watch what ARGUS sees."

*[The SAM 2 water mask paints the river surface cyan. Depth reading: "1.34m — ADVISORY."]*

"ARGUS just converted a traffic camera into a calibrated hydrological instrument. Depth. Velocity. Uncertainty band. No hardware. No procurement cycle. No installation. Just a software agent reading what the camera already sees."

*[Load the 2023 Himachal Pradesh flood footage. Alert level climbs: Advisory → Watch → Warning.]*

*[Click to SHAP popup for Majuli Ward 7.]*

"And it tells you exactly why it thinks so."

*[Read aloud:]* "Water velocity three hundred and forty percent above normal — contributing forty-four percent to risk. Soil saturation at ninety-one percent — thirty-eight percent. Upstream tributary surge — eighteen percent."

"Every prediction. Fully explained. In language a District Collector can act on at two in the morning."

---

### [02:30–03:45] MINUTE 3 — THE BRAIN (Rogesh presents)

*[Slide: Causal GNN graph of Brahmaputra basin.]*

"Every flood system you have ever seen looks at this data and says: flood likely."

*[Pause.]*

"ARGUS asks a different question."

*[Type into the Interventional Query panel — slowly, so judges can see:
"Open Pandoh Dam Gate 2 to 25%"]*

*[Click "Compute Intervention." Wait 2 seconds.]*

*[Result appears: Baseline 4.7m → Intervened 3.1m. Damage reduction 34%. Confidence 89%. Act within 47 minutes.]*

"This is not a prediction. This is a lever."

"ARGUS has just handed the District Collector a specific action — and a mathematical proof, derived from Judea Pearl's causal framework, of exactly what happens when they pull it."

"Thirty-four percent damage reduction. Forty-seven minutes to act."

"No other flood system in the world does this."

---

### [03:45–04:45] MINUTE 4 — THE VOICE (Dhana manages props)

*[Rogesh reaches across and visibly unplugs the WiFi cable from the laptop.]*

"The internet just died."

*[Pause. Let the silence land.]*

"In every major flood — Assam 2022, Himachal 2023, Sikkim 2023 — the towers flood before the people can be warned. The very infrastructure we use to warn people is the first thing the disaster destroys."

*[Show ACN status widget: "CLOUD MODE → OFFLINE — ORACLE ACTIVE"]*

"ARGUS's Autonomous Crisis Node — a five-thousand-rupee Raspberry Pi in the district emergency office — just switched to its village-personalized AI model. It has detected the flood independently. And now it acts."

*[LoRaWAN siren trigger fires on screen.]*

*[The judge's phone rings. Answer it on speaker.]*

*[An Assamese voice plays the evacuation instruction.]*

"The internet is still down. The siren is ringing. And the village elder just received a personalized evacuation instruction in Assamese — telling them exactly which road to take and which shelter has space."

*[Reconnect the WiFi cable.]*

"ARGUS cannot be blinded."

---

### [04:45–05:45] MINUTE 5 — THE PLAN (Switch to Evacuation tab)

*[Slide: Majuli island evacuation map. Village dots colored by risk.]*

"ARGUS does not stop at the warning."

*[Zoom to Majuli Ward 7.]*

"Two thousand, three hundred and forty people. ARGUS has assigned Bus AS-01-CD-8872, departing in twenty-two minutes, via NH-715. That road closes in sixty-seven minutes. ARGUS knows this. The plan does not send them down a road that floods."

*[Show shelter occupancy: Jorhat Community Hall 0/400.]*

*[Show WhatsApp audio notification sent to Sarpanch.]*
*[Show NDRF API webhook firing.]*
*[Show traffic signal override.]*

"Every person in that village has a seat. A route. A shelter. And seventy-eight minutes to get there safely."

"This is not a warning. It is a rescue — scheduled in advance."

---

### [05:45–06:30] MINUTE 6 — THE MONEY (Switch to FloodLedger tab)

*[Slide: Deck.gl map. Yellow pin — insured tea estate. Red flood polygon expanding.]*

"When the satellite confirms this flood polygon..."

*[Click "Simulate Flood Event."]*

*[Smart contract fires. Terminal shows: tx_hash. Payout: ₹14,70,000. Confirmed.]*

"No claims adjuster. No six-month dispute. No paperwork."

"The moment satellite data confirms the flood — which it always does within twenty-four hours — the contract self-executes. The tea estate owner receives their payout. The insurance company saves four lakh rupees in claims processing cost. And ARGUS earns an API fee for every trigger."

"ARGUS is not a government budget line hoping for annual renewal. It is climate infrastructure that insurance markets will pay to keep running — because every payout it automates saves them more than it costs."

---

### [06:30–07:00] MINUTE 7 — THE CLOSE (Rogesh presents)

*[Switch to MIRROR panel. Show the Himachal Pradesh backtest timeline slide.]*

"August fourteenth, twenty twenty-three. Himachal Pradesh."

*[Slide shows the two-row timeline. Top: flat grey. Bottom: alive with ARGUS signals.]*

"Official system: first warning at T minus eight minutes."

*[Highlight the flat grey row.]*

"ARGUS: first signal at T minus one hundred and eighty minutes."

"Evacuation dispatched at T minus seventy-eight."

"Estimated lives saved: forty to forty-seven. Out of seventy-one."

*[Long pause. Look at judges.]*

*[Click to final slide: world map with ARGUS nodes.]*

"Five thousand sensors just broke under the mud."

*[Pause.]*

"ARGUS turned every surviving camera into a gauge."

*[Pause.]*

"When the towers fell, the crisis nodes kept warning."

*[Pause.]*

"When the water hit, every village had a plan."

*[Pause.]*

"And when the flood was over — MIRROR told the government exactly which decision, made ninety minutes earlier, would have saved forty lives."

*[Three-second silence. Eyes up. Shoulders back.]*

**"Every flood system in the world tells you a flood is coming."**

*[Pause.]*

**"ARGUS tells you what to do about it."**

*[Pause.]*

**"ARGUS cannot be blinded."**

*[Step back. Do not speak. Hold the silence for five full seconds.]*

---

## Timing Budget

| Moment | Target | Hard Max | Speaker |
|---|---|---|---|
| Hook (water pour) | 90s | 100s | Rogesh |
| CV Gauging + SHAP | 55s | 70s | Dhana |
| Causal Intervention | 70s | 80s | Rogesh |
| WiFi Kill | 55s | 65s | Dhana |
| Evacuation Plan | 55s | 65s | Sabarish |
| FloodLedger | 45s | 55s | Sabarish |
| Close | 30s | 35s | Rogesh |
| **Total** | **6:40** | **7:30** | |

## Emergency Adjustments

**If running long:** Cut the SHAP explanation to one factor. Cut the shelter occupancy detail in Minute 5.

**If running short:** Extend the silence after the closing line. Silence is confidence.

**If demo crashes:** Dhana immediately switches to the backup video. Rogesh says: "Let me show you what this looks like in practice" — and narrates over the video. Never apologize for technology.

**If a judge interrupts with a question mid-demo:** Answer in one sentence. Then say: "I'll cover that in detail in just a moment." Return to the script.
