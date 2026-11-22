# Expansion plan (merged from Sol v2 and Neon v2, Saturday ~22:00)

Sources: [../research/sol_v2.md](../research/sol_v2.md) and [../research/neon_v2.md](../research/neon_v2.md). Where they agree, the idea is in; where only one proposed it, the effort and demo value decide.

## The new story

**Before:** a wearable with a sepsis score, NEWS2 and an SBAR card.

**After:** **an offline sepsis safety net for people sent home in a high-risk window**, such as after surgery or during the 7 to 14 days after chemotherapy. It does four things:

1. **Watches trends** with Edge Impulse models running on the UNO Q.
2. **Never lets a model veto a human.** One tap for "I feel unwell" or "something is wrong", and hard rules such as 38 °C after chemotherapy, escalate whatever the score says.
3. **Hands the case to a named nurse,** who accepts it on a second screen. The wearer sees who has it and when.
4. **Keeps working with the internet cut,** and shows plainly which readings are stale or missing.

Both reports independently said our ceiling is the *pathway*, not the model. A score alone leaves someone at home not knowing what to do.

## What both peers proposed (build these)

| # | Feature | Sol | Neon | Sunday effort | Owner |
|---|---|---|---|---|---|
| 1 | **Fix the model's training target and re-benchmark honestly** (v2 trains on onset−24..onset−1; report catch, separate alerts and alarm hours, plus age and sex subgroups) | #1 | S1, S4 | 2 h (running now) | main thread |
| 2 | **Owned handoff:** an alert becomes a task (pending → accepted → resolved) with a named nurse, timestamps and an action; second-screen nurse page; the wearer sees the receipt | #2 | S5 (as FHIR QR) | 3 h | agent A |
| 3 | **"I feel unwell" / Martha's Rule button + pathway profiles:** post-surgery, chemotherapy (temperature 38 °C or more → oncology hotline card immediately, NICE CG151), care home (soft signs) | #7, #8 | S6 | 1.5 h | agent A |
| 4 | **Outage and stale-data demo:** cut the internet and models keep running; watch disconnects and readings visibly age; deterministic fault fixtures | #3 | S5 | 2 h | board thread |
| 5 | **"What if" stress lab on replay:** SpO2 over-read by 2 to 4 points (darker skin), missing SpO2, beta-blocker-capped HR, a walk; shows how NEWS2 and the model shift | #5 | S3, S4 | 2.5 h | agent B |
| 6 | **Personal baseline:** resting HR and RMSSD against the wearer's own time-of-day normal (context, not scored) | #4 | S7 | 1.5 h | board thread |
| 7 | **Speech attention check** (digits backwards, Edge Impulse audio model) feeding the confusion item, plus a tap fallback | #7 (optional) | S8 | in progress | main thread |
| 8 | **Offline FHIR export:** the handoff as FHIR R4 `Task` + `Observation` JSON, plus a QR code a paramedic can scan | #2 roadmap | S5 | 1.5 h | agent A |

## Stretch or roadmap (only if time allows)

- **Motion model on the STM32 itself.** Neon's "dual brain" idea: an Edge Impulse C++ library on the microcontroller, with the Linux `.eim` as fallback. Strong Edge Impulse story; timebox 90 min.
- **Camera respiratory rate or capillary refill on localhost.** Sol and Neon each proposed a camera feature; both are risky.
- **Small on-device language model** for plain-English carer instructions. Unverified on 2 to 4 GB of RAM; roadmap.
- **Moonshots:**
  - Sol: a virtual-ward service measured by time to accepted review; a home-to-A&E paired cohort; a wearable that asks for the most informative next observation.
  - Neon: a home sepsis cohort with a digital twin; cuffless shock sensing from the watch's ECG, PPG and BIA; a low-cost care-home and low-resource kit.

## Fixed already (found by Neon)

- The board rejected every watch packet with HTTP 400 because of the new `ambient_c` and `ibi_ms` fields. Fixed; the board now computes RMSSD.
- The v1 model was trained on the wrong hours. The v2 retrain is running.

## Pitch (3 min)

1. **0:00–0:25.** Who is at risk at home between checks: post-surgery or chemotherapy patients.
2. **0:25–1:00.** Live: the chest-strap breathing estimate drops out during movement and comes back; cut the internet and everything keeps running.
3. **1:00–1:40.** Replay a recorded ICU case. The alert becomes a task, and the nurse accepts it on the second screen.
4. **1:40–2:15.** Stress lab: the same case with an SpO2 over-read. Honest about what fails.
5. **2:15–3:00.** One slide of results (catch rate, separate alerts, alarm hours, subgroups), then the ask: a shadow virtual-ward pilot.
