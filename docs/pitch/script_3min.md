# 3-Minute Pitch Script

**Target pace:** ~435 spoken words (~145–150 words/min) with built-in beats for live hardware and screen transitions.  
**Core message:** An offline sepsis safety net for people sent home after surgery or chemotherapy — combining on-device Edge Impulse models, partial NEWS2, hard rules no model can veto, and an owned nurse handoff.  
**Tone:** Calm, clinical, ruthlessly honest. Never claim diagnosis, home validation, or beating NEWS2 at equal alarm time.

---

## Side-by-Side Script

| Time | Slide / Screen | Spoken Lines (Word-for-Word) | On-Screen / On-Device Action | Fallback Line (If Step Fails) |
|---|---|---|---|---|
| **0:00 – 0:25** | **Slide 1:** The Gap After Discharge | "In the UK, sepsis causes around 245,000 cases and 48,000 deaths a year [1]. The dangerous gap is at home after surgery or chemotherapy, between routine checks — where a score alone leaves someone stuck at 2 a.m. So we built an **offline sepsis safety net**: decision support, not a diagnosis, and no model ever vetoes a human." | Hold up Galaxy Watch 8 on wrist and UNO Q + Modulino Movement on chest strap. Keep Slide 1 visible. | *(No live tech required in this beat.)* |
| **0:25 – 0:55** | **Live Screen 1:** `http://<BOARD_IP>:8000/` (Monitor Dashboard) | "Here it is live. A Galaxy Watch 8 streams heart rate, resting beat intervals, wrist skin temperature — labelled *not* core temperature — and spot SpO₂. On my chest, an Arduino UNO Q and Modulino Movement estimate breathing rate. When I move, breathing rate drops out and says *moving* instead of guessing. When I'm still, it returns. Cut the internet — the offline banner appears, and our Edge Impulse `.eim` keeps scoring locally with zero cloud." | 1. Point to live HR & skin-temp cards.<br>2. Move/sway 5 s so RR shows `moving`.<br>3. Sit still briefly so resting indicator / RR recovers.<br>4. Cut hotspot mobile data (or click **Cut the internet (simulated)**) — point to **Offline** banner and **Edge Impulse model on the board, running** chip. | **If RR won't settle:** "Breathing rate requires 20 seconds of still rhythm and three agreeing windows — refusing to guess under motion is deliberate."<br>**If Watch drops:** "Notice the liveness chip turns amber and readings visibly age — the watch buffers up to an hour locally."<br>**If hotspot drops LAN:** Switch to laptop simulator (`127.0.0.1:8000`): "Venue RF dropped the board link; I'm switching to the identical Python and model stack on this laptop." |
| **0:55 – 1:40** | **Live Screen 1** (`/` Replay) + **Second Screen** (`/handoff` Nurse Queue) | "Trend scoring needs eight hours of history, so we don't fake sepsis on me. We run a labelled replay — *Recorded ICU case, accelerated* — of held-out PhysioNet patient `p112060` through the board's `.eim`. As vitals drift, the model alerts 24 hours before onset while NEWS2 stays quiet — illustrative, not typical. That alert opens a tracked task with SBAR and an offline FHIR R4 QR code. On the second screen, Nurse Sam accepts it — and the wearer sees who owns their alert and when. Meanwhile, tapping *I feel unwell* or entering 38 °C after chemotherapy escalates immediately, whatever the model says." | 1. Select `p112060` at `1.5 s/h` → click **Start replay**.<br>2. Point to purple **REPLAY** banner and curve crossing `55%`.<br>3. On Screen 2 (`/handoff`), enter `Sam` → click **Accept task**; optionally click **Paramedic QR**.<br>4. Point to wearer receipt / pathway check-in ("I feel unwell" or NICE CG151 38 °C rule [3]). | **If `.eim` falls back to trees:** "Our pure-Python tree fallback kicked in — identical to the `.eim` to four decimal places, so scoring never halts."<br>**If Screen 2 fails to sync:** Show the SBAR escalation card directly on Screen 1: "The board still generates the full SBAR and FHIR handoff locally."<br>**If board crashes:** Switch to laptop simulator (`board/sepsis-monitor/sim/`) or 90-second backup video. |
| **1:40 – 2:10** | **Live Screen 1:** `http://<BOARD_IP>:8000/stress` (What-If Stress Lab) | "Our stress lab exposes where both methods fail across all 7,898 held-out patients. Simulate a +4 SpO₂ over-read — illustrating darker-skin oximeter bias [2] — and NEWS2 loses 5 points of catch rate. Our model doesn't drop there, though honestly that looks like an ICU oxygen artefact, not true robustness. Where *our* model breaks hardest is removing core temperature: catch rate falls 22 points, from 78% to 55%." | 1. Open `/stress`.<br>2. Select **SpO2 over-read +4** → highlight NEWS2 `71% (−5)` in table.<br>3. Switch to **No core temperature** → highlight Model `55% (−22)` vs NEWS2 `73% (−3)`. | **If `/stress` is slow or fails:** Flip immediately to **Slide 4 (Stress Lab Table)** and cite the exact same two rows from `docs/stress_results.md`. |
| **2:10 – 2:45** | **Slide 5:** Honest Evidence + **Slide 6:** Edge Impulse Story | "Here's the honest benchmark on 7,898 held-out ICU patients, cutoffs chosen on validation only. At 0.55, matching NEWS2's catch rate — 78% versus 76% — our Edge Impulse BYOM LightGBM raises **43% fewer separate false alerts** and warns **three hours earlier**. The trade-off: alerts last longer (22% vs 16% of hours), so at equal alarm time NEWS2 catches more, especially without core temp — which is why we run both. We also built an Edge Impulse spoken-digit confusion check, after rejecting a slurred-speech model that failed on unseen speakers." | Hold **Slide 5** (4-vital & 3-vital tables from `docs/results.md`). At 2:32, advance to **Slide 6** (two EI projects + rejected TORGO model). | *(Slides only — zero live dependency.)* |
| **2:45 – 3:00** | **Slide 7:** Path to Clinic & The Ask | "This is retrospective ICU data, not home validation, and a prototype, not a medical device. Next, we want an NHS virtual-ward partner for a **shadow-mode pilot** under MHRA and DCB0129/0160 governance [4, 5] — measuring real home signals and nurse workload. Thank you." | Hold on **Slide 7** (pilot roadmap + ask). Stop at 2:58. | *(If 10 s behind at 2:40, drop the last sentence of Slide 6 and jump straight to Slide 7.)* |

---

## Pacing Checkpoints

- **0:25** — Off Slide 1, live dashboard on screen.
- **0:55** — Click **Start replay** on `p112060` (alerts at hour 89, ~9 s after hour 83 starts at 1.5 s/h).
- **1:40** — On `/stress` (or Slide 4 fallback).
- **2:10** — On Slide 5 (Honest Evidence). Never rush the trade-off.
- **2:45** — On Slide 7 (The Ask) for a hard 3:00 finish.

## External Sources Cited in Script

1. UK Sepsis Trust (~245,000 cases, ~48,000 deaths/year in UK): <https://sepsistrust.org/about/about-sepsis/>
2. Sjoding MW et al., *N Engl J Med* 2020;383:2477–2478 (~3× occult hypoxaemia in Black vs White patients): <https://doi.org/10.1056/NEJMc2029240>
3. NICE CG151 (Neutropenic sepsis urgent oncology pathway): <https://www.nice.org.uk/guidance/cg151>
4. UK MHRA Software and AI as a Medical Device Change Programme: <https://www.gov.uk/government/publications/software-and-ai-as-a-medical-device-change-programme>
5. NHS England Digital Clinical Risk Management Standards (DCB0129 / DCB0160): <https://digital.nhs.uk/services/clinical-safety/clinical-risk-management-standards>
