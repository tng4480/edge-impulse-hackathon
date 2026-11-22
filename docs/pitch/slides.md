# Pitch Slide Outline (7 Slides · 3 Minutes)

Every internal performance number comes strictly from `docs/results.md` and `docs/stress_results.md`. Every external number cites its source URL.

---

## Slide 1 — The Gap Between Discharge and A&E
- **Timing:** 0:00 – 0:25
- **One message:** **High-risk patients sent home after surgery or chemotherapy deteriorate between checks — and a raw score alone leaves them stuck wondering what to do.**
- **Visual to show:** Simple timeline graphic: *Hospital discharge → 7–14 day home risk window (gap between checks) → Emergency readmission*, contrasted with our four-part safety net (*Watch trends locally · Human overrides AI · Named nurse accepts · Works offline*).
- **Numbers to quote & sources:**
  - **~245,000** UK sepsis cases and **~48,000** sepsis-related deaths per year ([UK Sepsis Trust](https://sepsistrust.org/about/about-sepsis/)).
  - Target window: **7–14 days** post-chemotherapy or post-surgical discharge (finite loaner window; [NHS England Virtual Wards](https://digital.nhs.uk/data-and-information/information-governance/guidance/virtual-wards), [NICE CG151](https://www.nice.org.uk/guidance/cg151)).

---

## Slide 2 — Architecture: Offline Safety Net & Honest Hardware Limits
- **Timing:** 0:25 – 0:30 *(quick visual anchor before switching to live demo, or print as reference)*
- **One message:** **Every sensor, model, rule, and handoff runs locally on an Arduino UNO Q — with every hardware limit labelled in plain sight.**
- **Visual to show:** Clean left-to-right block diagram:
  1. **Inputs:** Galaxy Watch 8 (continuous HR, IBI/RMSSD context, wrist skin temp *[context only — not core]*, spot SpO₂) + Arduino UNO Q + Modulino Movement (25 Hz chest IMU → motion-gated breathing rate).
  2. **On-Board Brain (Zero Cloud):** Edge Impulse BYOM LightGBM `.eim` + 4-vital partial NEWS2 + Hard pathway rules (NICE CG151 ≥ 38 °C oral temp, *"I feel unwell"* / Martha's Rule — no model can veto).
  3. **Actionable Handoff:** Named nurse queue (`pending → accepted → resolved`), wearer receipt, SHA-256 append-only audit log, and offline FHIR R4 QR code.
- **Numbers to quote & sources:**
  - Chest IMU sampled at **25 Hz**; respiratory rate gated when motion > **0.03 g**; requires **20 s** + 3 agreeing windows (`board/sepsis-monitor/sketch/sketch.ino`, `board/sepsis-monitor/python/resp.py`).
  - Watch buffers up to **1 hour** if board link drops (`wearos/README.md`).
  - **Explicit disclaimer box:** *Not measured: blood pressure, core temperature (unless entered manually), supplemental O₂. Modulino Thermo/Light/Vibro not currently connected.*

---

## Slide 3 — Live Demo Cue Card *(Backdrop While Switching Screens)*
- **Timing:** 0:25 – 1:40 *(stay on live screens; show this slide only during transitions or if live screens fail)*
- **One message:** **Watch real motion rejection, offline inference, an accelerated ICU replay, and a named nurse accepting the case on a second screen.**
- **Visual to show:** 4-step visual strip matching the live demo beats:
  1. **Live chest IMU:** Move → RR drops out (`moving`); sit still → returns.
  2. **Internet cut:** Offline banner on; Edge Impulse `.eim` keeps running locally.
  3. **Labelled ICU replay (`p112060`):** *"Recorded ICU case · accelerated"* — model alerts 24 h before onset (illustrative, not typical).
  4. **Owned handoff + override:** Nurse Sam accepts on Screen 2 → wearer sees receipt; *"I feel unwell"* / 38 °C chemo rule always escalates.
- **Numbers to quote & sources:**
  - Replay case `p112060`: hours **83–115** (~50 s at 1.5 s/h); model ≥ 0.55 alerts at **hour 89** (**24 h** before onset at hour 113); NEWS2 rule does not alert in that window; median-lead among 28 qualifying cases (**illustrative, not typical**). Negative control: `p000147` (neither alerts) (`docs/results.md`).

---

## Slide 4 — What Breaks in the Real World: Stress Lab
- **Timing:** 1:40 – 2:10 *(live `/stress` screen preferred; fall back to this slide directly if needed)*
- **One message:** **We stress-tested both methods across all 7,898 held-out patients — exposing where NEWS2 breaks and where our own model breaks hardest.**
- **Visual to show:** Side-by-side compact table (highlighting the two red callouts: NEWS2 on SpO₂ over-read, Model on No core temp & Beta-blocker):

| Simulated Stressor (476 sepsis, 7,422 non-sepsis) | Model ≥ 0.55 Flagged | NEWS2 Flagged | Model Alarm Time | NEWS2 Alarm Time |
|---|---:|---:|---:|---:|
| **Baseline (4 recorded ICU vitals)** | 78% (±0) | 76% (±0) | 22% (±0) | 16% (±0) |
| **SpO₂ over-read +4** *(Sjoding NEJM 2020 illustration)* | 80% (+2)* | **71% (−5)** | 25% (+3) | 13% (−3) |
| **Beta-blocker (HR capped at 80)** | **67% (−11)** | 73% (−3) | 17% (−5) | 14% (−2) |
| **Walk burst (2 h, non-sepsis only)** | n/a *(1.11 FA/d, +0.20)* | n/a *(1.90 FA/d, +0.29)* | 25% (+3) | 19% (+3) |
| **No core temperature** *(live wearable reality)* | **55% (−22)** | 73% (−3) | 13% (−9) | 15% (−1) |

- **Numbers to quote & sources:**
  - All numbers from `docs/stress_results.md` (`training/out/stress_eval.json`).
  - \*Footnote on slide: *Model's +2 pts under SpO₂ +4 is **not** true robustness (likely an ICU supplemental-O₂ artefact); neither method corrects optical skin-tone bias.*
  - Sjoding et al., *N Engl J Med* 2020 (~3× occult hypoxaemia in Black vs White patients): [doi:10.1056/NEJMc2029240](https://doi.org/10.1056/NEJMc2029240).

---

## Slide 5 — Honest Evidence: Held-Out PhysioNet 2019 Benchmark
- **Timing:** 2:10 – 2:30
- **One message:** **Matching NEWS2's catch rate, our model raises 43% fewer separate false alarms and warns 3 hours earlier — but it does not beat NEWS2 on catches per alarm-hour, especially without core temperature.**
- **Visual to show:** Two clean comparison tables side by side — **Left:** 4 ICU vitals; **Right:** 3 vitals (no core temp) — with one prominent callout banner: *"Retrospective ICU data · cutoffs chosen on validation patients only · model score, not a diagnosis."*
- **Numbers to quote & sources** *(all from `docs/results.md`, `training/out/strict_eval.json`, `training/out/strict_eval_v3.json`)*:
  - **Test cohort:** **476 sepsis** and **7,422 non-sepsis** held-out PhysioNet 2019 patients (validation split for cutoffs: **184 sepsis**, **2,926 non-sepsis**; [PhysioNet 2019](https://physionet.org/content/challenge-2019/1.0.0/)).
  - **4 vitals (HR, SpO₂, Temp, RR):**
    - NEWS2 rule (5+ or any 3): **76%** flagged | **1.61** separate false alerts/day | **16%** alarm time | **17 h** median lead
    - **Model ≥ 0.55 (on device):** **78%** flagged | **0.91** separate false alerts/day (**−43%**) | **22%** alarm time | **20 h** median lead (**+3 h**)
    - Model ≥ 0.61 (equal alarm time): **70%** flagged | **0.72** separate false alerts/day | **15%** alarm time | **18 h** median lead
  - **3 vitals (no core temperature — retrained v3, not deployed):**
    - NEWS2 (3 vitals): **73%** flagged | **1.58** false alerts/day | **15%** alarm time | **17 h** median lead
    - Model v3 ≥ 0.52: **78%** flagged | **1.06** false alerts/day | **32%** alarm time | **23 h** median lead
    - Model v3 ≥ 0.61 (equal alarm time): **60%** flagged | **0.68** false alerts/day | **16%** alarm time | **19 h** median lead
  - **Window-level context (1,200 identical test windows):** LightGBM **0.745 ROC AUC** vs EI Dense NN **0.698** vs 4-vital NEWS2 **0.642**.

---

## Slide 6 — How We Used Edge Impulse (And What We Said No To)
- **Timing:** 2:30 – 2:45
- **One message:** **Two Edge Impulse `.eim` models running offline on UNO Q — and disciplined evaluation that made us kill a model that didn't generalise.**
- **Visual to show:** Three-column card layout:
  1. **Project 1 — Sepsis Risk (BYOM):** 176-tree LightGBM (32 trend features) → Hummingbird GEMM ONNX → Edge Impulse BYOM (impulse #4) → Linux aarch64 `.eim` on UNO Q (matches LightGBM to 4 dp; pure-Python fallback identical).
  2. **Project 2 — Confusion Attention Check (Native Audio KWS):** Speaker-disjoint Speech Commands v2 (12 classes) → 16 kHz Audio MFCC → Keras `int8` `.eim` (**89.6% val acc**) for backwards-digits check (NEWS2 "C") + tap/carer fallback.
  3. **Tested & Rejected — Slurred-Speech Classifier:** TORGO leave-one-speaker-out gave **0.635 clip AUC**, mic bias (0.669 vs 0.592), and missed dysarthric `F03` on **93%** of clips → **rejected** (`docs/research/speech.md`).
- **Numbers to quote & sources:**
  - Sepsis window AUC: **0.745** (LightGBM) vs **0.698** (EI Dense NN) (`docs/results.md`).
  - Speech digits `int8` val acc: **89.6%** (`training/out/speech_train.log`; dataset [arXiv:1804.03209](https://arxiv.org/abs/1804.03209)).
  - Rejected TORGO dysarthria baseline: **0.635** clip AUC, **0.77** speaker-mean AUC, **93%** missed on `F03`, **0.64** false score on healthy `MC04` (`docs/research/speech.md`; bias discussed in [arXiv:2509.19946](https://arxiv.org/abs/2509.19946)).

---

## Slide 7 — Path to Clinic & The Ask
- **Timing:** 2:45 – 3:00
- **One message:** **We don't ask anyone to trust an ICU model at home — we ask for a shadow-mode NHS virtual-ward pilot to measure real home signals and real nurse workload.**
- **Visual to show:** 3-step roadmap arrow:
  1. **Today (Prototype):** Offline UNO Q + Watch 8, honest ICU benchmark, FHIR R4 QR, append-only audit trail. *Not a medical device.*
  2. **Next (Shadow Pilot):** 100–200 post-surgery / post-chemo virtual-ward patients in **shadow mode** (silent logging + paired oral temp, BP spot checks, skin-tone audit) under **DECIDE-AI** evaluation ([PMC9116198](https://pmc.ncbi.nlm.nih.gov/articles/PMC9116198/)).
  3. **Clinical Deployment:** UK **MHRA SaMD / AIaMD** regulatory dossier + NHS **DCB0129 / DCB0160** clinical safety case + dedicated washable chest patch.
- **Numbers to quote & sources:**
  - **The Ask:** An NHS virtual-ward or acute-oncology clinical partner (and Clinical Safety Officer) to scope a shadow-mode study measuring **time to accepted review**, **false-review workload**, and **home-to-A&E sensor calibration**.
  - External references: [UK MHRA SaMD/AIaMD Change Programme](https://www.gov.uk/government/publications/software-and-ai-as-a-medical-device-change-programme), [NHS DCB0129 / DCB0160](https://digital.nhs.uk/services/clinical-safety/clinical-risk-management-standards), [NHS England Martha's Rule](https://www.england.nhs.uk/patient-safety/marthas-rule/).
