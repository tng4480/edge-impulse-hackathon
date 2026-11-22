# Scope-Expansion Strategy: From Sepsis Prototype to Offline Edge-AI Sentinel

*Grounded in codebase inspection (`board/`, `training/`, `wearos/`, `samsung-health-sensor-api-1.4.1.aar`), a fresh held-out audit of our 7,898 PhysioNet 2019 test patients, and primary-source verification. Every shortlisted dataset URL & licence was live-fetched (HTTP 200) unless flagged.*

---

## 1. Diagnosing the Ceiling: What Stops Judges Saying "Wow"

1. **User & Clinical-Wedge Ceiling:** Pitching "a home sepsis wearable for adults" triggers scepticism—healthy adults won't strap an Arduino daily, and delirious patients ignore alerts. Worse, our subgroup audit on the 7,898 held-out test patients (`training/out/model.json`, cutoff `0.55`) uncovered a **−12.9 pp age-equity cliff**: sensitivity is **83.2%** (`<50`) and **78.2%** (`50–74`), but drops to **70.3%** in **`≥75`s** (worse than 4-vital NEWS2's **77.5%**), alongside a **−6.2 pp sex gap** (**73.8%** female vs **80.0%** male). Elderly septic patients mount blunted fever/HR spikes and present with delirium first.
2. **Data & Modelling Ceiling (Why We Lose at Equal Alarm Hours):** LightGBM wins window AUC (`0.745` vs `0.642`) yet trails NEWS2 at equal alarm hours (`69.5%` vs `76.1%`). Code + test audit proved three causes:
   - **Train/eval bug (`training/train_gbm.py:44–46`):** Positives sample all `SepsisLabel==1` hours through shock (`e >= onset`), while negatives include `e <= fp - 12 = onset - 18`—labelling sepsis patients' `[onset−24..onset−18]` pre-onset hours as `y = 0`!
   - **Sticky 24 h latches (`features.py:45–50`):** 20/32 features are 24 h aggregates (`min`/`max`/`mean`), stretching mean false-alert episodes to **5.85 h vs NEWS2's 2.39 h** (`2.45×`); **10% of non-sepsis patients burn 49.7% of all alert hours**.
   - **Missing physiology & external validation:** No personal baselines, cross-vital ratios, `Age`, or external hospital cohort.
3. **Pathway & Interop Ceiling:** No NHS handoff (FHIR UK Core R4 / 111 / paramedic scan), no **NICE CG151** 1 h neutropenic bypass, no **Martha's Rule** carer trigger, and no optical **SpO₂ skin-tone bias** guard. *(Live bug: `Vitals.kt:49` already emits `ambient_c` and `ibi_ms`, but `main.py:54` `WATCH_ALLOWED` rejects both with HTTP 400!)*
4. **Demo Ceiling:** Passive ICU replay feels static; judges cannot inject real home failure modes (walking, dark-skin SpO₂ bias, beta-blockers, WAN drop, delirium) and watch naive rules fail live.
5. **Edge Impulse & UNO Q Ceiling:** One BYOM Linux `.eim` leaves **STM32U585 Cortex-M33**, **LSM6DSOX gyro (`0x22`)**, and Edge Impulse's **GMM Anomaly Detection**, **Performance Calibration**, **Data Explorer**, and **EON Tuner** idle—missing the story that **Qualcomm acquired Edge Impulse (10 Mar 2025)** and **announced acquiring Arduino (7 Oct 2025)** alongside the **Dragonwing QRB2210 + STM32U585 UNO Q**.

---

## 2. Sixteen Distinct Expansion Routes

| # | Route | Summary | Fit | Pick |
|---|---|---|---|---|
| **1** | **Honest NEWS2-Beater v2 + `eICU-Demo`** | Pre-onset fix, personal z-score/CUSUM, cross-vital ratios, `Age`, 20-hospital test | Sun | **★ S1** |
| **2** | **Dual-Brain EI on UNO Q (MCU + MPU)** | 6-axis gyro IMU + **GMM Anomaly** on **STM32U585**, `.eim`s on **QRB2210**, **EON Tuner** | Sun | **★ S2** |
| **3** | **"Home-Reality Digital Twin" Lab** | 6 live home-stressor toggles on PhysioNet + BioGears 48 h sepsis vs NEWS2 | Sun | **★ S3** |
| **4** | **Age & Skin-Tone Equity Shield** | Close −12.9 pp ≥75 cliff; chest-RR primacy + ΔSpO₂ + 93–96% occult-hypoxemia guard | Sun | **★ S4** |
| **5** | **Offline FHIR UK Core R4 + SHC QR & DCB0129 Log** | Zero-cloud LAN enclave + Version ≤22 QR (FHIR/SNOMED/SBAR) + SHA-256 audit | Sun | **★ S5** |
| **6** | **Wedge Pack: Chemo CG151 + RESTORE2 + Martha's Rule** | 7–14 d chemo nadir bypass, care-home Soft Signs + 4AT, carer override (`UKCore-Flag`) | Sun | **★ S6** |
| **7** | **Zero-Hardware Perfusion & Autonomic Fusion** | Watch `ibi_ms` RMSSD, passive orthostatic ΔHR, localhost/HTTPS nailbed CRT | Split | **★ S7** |
| **8** | **Multi-Task Voice & Audio Suite** | 4AT digits-backwards + **EI Performance Calibration** + SBCT + roadmap cough MFE | Split | **★ S8** |
| **9** | **Postpartum Maternal Sepsis (NICE NG255/MEWS)** | 4P Study postpartum HR curve (84→75 bpm) + stable RR targeting 2.72× Black maternal disparity (MBRRACE-UK); needs £20 BLE BP cuff | Road | — |
| **10** | **Bounded Carer Translation SLM (`llama.cpp`)** | `SmolLM2-360M`/`Qwen2.5-0.5B` Q4_K_M on **4 GB UNO Q** strictly translating frozen SBAR w/ regex numeric checks; unsafe for triage ([Hager *Nat Med* 2024](https://doi.org/10.1038/s41591-024-03097-1)) & OOM-risky on 2 GB | Road | — |
| **11** | **90-Day Post-Sepsis Survivor Loaner** | Targets **42.7% 90-day readmission** ([Prescott *JAMA* 2015](https://doi.org/10.1001/jama.2015.1410)) w/ discharge-calibrated passive loaner kit | Road | — |
| **12** | **LMIC / Rural CHW £75 Spot-Triage Kit** | Swaps £319 Watch 8 for £15 clip oximeter + chest IMU into £60 offline UNO Q for 85% LMIC burden ([Rudd *Lancet* 2020](https://doi.org/10.1016/S0140-6736(19)32989-7)) | Road | — |
| **13** | **Circadian & Sickness-Behaviour GMM** | Multi-day resting HR/temp/upright-hours anomaly flagging quiet bedbound decline (`TIHM` + `BIG IDEAs` + `Capture-24`) | Road | — |
| **14** | **Watch 8 `ECG_MV` + `PPG_GREEN` PAT/AFib** | Single-clock `ValueKey$EcgSet` ECG+PPG (verified in `.aar`) for sepsis-triggered AFib & relative Pulse Arrival Time | Road | — |
| **15** | **Care-Home Wing Hub (1 UNO Q : 10 Beds)** | One £60 hub polls 10 BLE sensors w/ corridor triage queue, cutting per-bed capex 10× | Road | — |
| **16** | **Paediatric Patch Fork (NICE NG254/PEWS)** | 4 PEWS age bands + parental override; roadmap only (Watch 8 won't fit <13s; PhysioNet 2019 is adult-only) | Road | — |

---

## 3. Shortlisted Best 8 Routes

### S1. Honest NEWS2-Beater v2 (Personal-Delta + Cross-Vital Coupling + `eICU-Demo`)
- **What / Who / Why:** Replaces sticky 24 h latches with causal **lagged personal-baseline z-scores**, one-sided **CUSUM**, `Age`, 4-vital **NEWS2 features** (suppressing chronic NEWS2 false alarms), and clinical ratios: **Liebermeister fever-adjusted HR** (`HR−84−9·(Temp−37)`, [Karjalainen 1986](https://pubmed.ncbi.nlm.nih.gov/3718106/); `HR/Temp`, [Lin 2024](https://doi.org/10.1016/j.heliyon.2024.e28990)), **Pulse-Respiration Quotient** (`HR/RR`, [Scholkmann 2019](https://doi.org/10.3389/fphys.2019.00371)), and **room-air ROX/ROX-HR** (`SpO2/RR`, `SpO2/(RR·HR)`, [Goh 2020](https://doi.org/10.1186/s40560-020-00458-z)). Fixes `train_gbm.py:46` to strictly pre-onset positives (`[onset−18, onset−1]`) + hard-negative sampling + `eICU-Demo` test. Helps clinicians, COPD & elderly; turns an equal-alarm-hour loss into a validation-locked multi-hospital win.
- **Hardware & EI:** Pure Python `features.py`/`train_gbm.py` → Hummingbird ONNX → **Edge Impulse BYOM** → `Linux AARCH64` `sepsis_v2.eim` on QRB2210; ablate charting-frequency counts.
- **Verified Data (HTTP 200):** [PhysioNet 2019](https://physionet.org/content/challenge-2019/1.0.0/) (**CC BY 4.0**); [eICU-CRD Demo v2.0.1](https://physionet.org/content/eicu-crd-demo/2.0.1/) (**ODbL 1.0**).
- **Demo / Risks / Effort:** Strict-eval card beats 4-vital NEWS2 on episodes/day, alarm hours, and `eICU-Demo`. *Risks:* val peeking (lock once); `eICU-Demo` lacks hourly Sepsis-3 timestamps. **3 h (Sun)** | **Roadmap:** Credentialed [MC-MED](https://physionet.org/content/mc-med/1.0.1/) (PhysioNet Credentialed 1.5.0) + discrete-time hazard.

### S2. Dual-Brain Heterogeneous Edge Impulse on UNO Q (STM32U585 + QRB2210)
- **What / Who / Why:** Enables unused **LSM6DSOX 3-axis gyro (`CTRL2_G 0x11`, `OUTX_L_G 0x22`)** for 6-axis chest posture/breathing ([Jafari Tadi *Sci Rep* 2017](https://doi.org/10.1038/s41598-017-07248-y)). Runs an INT8 **EI Arduino/Zephyr C++ library** (`still`/`moving`/`shiver-like` + **`Anomaly Detection (GMM)`** strap-off) on **STM32U585** (160 MHz Cortex-M33, 786 KB SRAM, 2 MB Flash; <10% footprint), streaming gated state over `Bridge` while **QRB2210** runs sepsis + audio `.eim`s. Stops exertion/strap false alarms and proves Qualcomm's dual-brain EI+Arduino thesis w/ **EON Tuner** (M33 vs A53) + **Data Explorer** on Free tier.
- **Hardware & EI:** EI Project #2 (25–52 Hz 6-axis): `Time series` (4 s/0.5 s) → `Spectral Analysis` → `Classification (Keras)` + **`Anomaly Detection (GMM)`** → **EON Tuner** → Arduino/Zephyr library in `sketch.ino` (fallback: Linux `motion.eim` via `arduino:motion_detection`). Pre-seed from PAMAP2 chest IMU + 2 min acted `shiver-like`.
- **Verified Data (HTTP 200):** [PAMAP2](https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring) (**CC BY 4.0**); [Capture-24](https://ora.ox.ac.uk/objects/uuid:99d7c092-d865-4a19-b096-cc16440cd001) (**CC BY**); [GalaxyPPG](https://zenodo.org/records/14635823) (**CC BY 4.0**).
- **Demo / Risks / Effort:** Volunteer walks, shivers, then lifts the strap—STM32U585 gates walking RR in <5 ms, flags `shiver-like`, and spikes GMM anomaly on strap-off. *Risks:* Zephyr header friction (**90-min timebox** → instant `motion.eim` fallback). **3.5 h (Sun: 2.5 h EI+Linux + 1 h STM32)** | **Roadmap:** LSM6DSOX **15 µA MLC** + 208 Hz GCG.

### S3. Interactive "Home-Reality Stress-Test & Digital Twin" Lab
- **What / Who / Why:** Interactive judge bench applying **6 home stressors** to held-out PhysioNet + pre-baked **BioGears 48 h `SEInfection`** dynamic sepsis trajectories: *(1) 15-min walk*, *(2) +3% dark-skin SpO₂*, *(3) beta-blocker HR cap (~80 bpm)*, *(4) wrist cooling*, *(5) q4h spot-SpO₂ & 90-min gap*, *(6) COPD baseline*. Disarms "ICU ≠ home" live for judges & NHS CSOs using real `.eim` inference.
- **Hardware & EI:** Pure-Python `sim.py` feeding on-board `sepsis.eim` + toggles in `dashboard.html`; pre-compute 1–2 **BioGears `SepsisSevere_Gut`** CSVs offline.
- **Verified Data (HTTP 200):** [PhysioNet 2019](https://physionet.org/content/challenge-2019/1.0.0/) (**CC BY 4.0**); [BioGears](https://github.com/BioGearsEngine/core) (**Apache 2.0**; beats [Pulse](https://pulse.kitware.com/) **Apache 2.0** for 48 h dynamic progression); [NeuroKit2](https://github.com/neuropsychology/NeuroKit) (**MIT**).
- **Demo / Risks / Effort:** Judge toggles *"Darker skin (+3% SpO₂) + Beta-blocker + 15-min walk"*—naive NEWS2 misses sepsis at rest yet false-alarms walking, while our personalized `.eim` holds steady and warns early. *Risks:* label explicitly as *simulated stressors*. **2.5 h (Sun)** | **Roadmap:** Coupled `GalaxyPPG`+`BIG IDEAs` twin for **MHRA AI Airlock Phase 3**.

### S4. Health-Equity & Age/Skin-Tone Fairness Shield
- **What / Who / Why:** Closes our **−12.9 pp ≥75 cliff** (`Age` + deltas + 4AT) and counters **optical SpO₂ bias**—[Sjoding *NEJM* 2020](https://doi.org/10.1056/NEJMc2029240) proved **~3× occult hypoxemia** in Black patients (11.7–17.0% vs 3.6–6.2%), driving the **UK Whitehead Equity Review (11 Mar 2024, all 18 recs accepted)** and **FDA Jan 2025 Draft Guidance** (≥150 subjects, **Monk Skin Tone [MST]** + **ITA**, `<1.5%` bias). Gives melanin-invariant **chest-IMU RR** primacy, scores **ΔSpO₂**, and flags `93–96%` SpO₂ + rising RR with an **Occult-Hypoxemia Guard**. Helps elderly, female & Black/Brown patients; self-auditing and fixing our own `.eim` is rare rigor.
- **Hardware & EI:** Subgroup audit (`<50`/`50–74`/`≥75`/`F`/`M`) in `strict_eval.py`; S1 retrain w/ `Age`+deltas; 93–96% banner + Whitehead **Equity Model Card** (disclosing no race/MST in PhysioNet 2019).
- **Verified Data (HTTP 200):** [PhysioNet 2019](https://physionet.org/content/challenge-2019/1.0.0/) (**CC BY 4.0**); [BOLD v1.0](https://physionet.org/content/blood-gas-oximetry/1.0/) (**PhysioNet Credentialed 1.5.0**, roadmap; *`openoximetry.org` 403 / slug 404—unverified*).
- **Demo / Risks / Effort:** Fairness Card shows ≥75 sensitivity restored above NEWS2, and `94%` SpO₂ + rising chest RR flags occult-hypoxemia uncertainty instead of NEWS2's silent `0 points`. *Risks:* never claim mathematical optical correction without MST/ITA data. **1.5 h (Sun)** | **Roadmap:** Credentialed `BOLD`/OpenOximetry calibration + MST/ITA HEIA.

### S5. Offline FHIR UK Core R4 + SMART Health Card QR & DCB0129 Audit Trail
- **What / Who / Why:** Keeps all `.eim` inference, baselines, and a **SHA-256 hash-chained SQLite audit log** (**NHS DCB0129** & **MHRA Jun 2025 PMS**) inside the UNO Q LAN enclave (**UK GDPR Art. 9**). Escalation renders a **SMART Health Card–style Version ≤22 QR** (`≤1,195` chars via DEFLATE) encoding compact **FHIR UK Core R4** (`UKCore-Observation-VitalSigns` w/ verified **SNOMED CT + LOINC**: NEWS2 `1104051000000101`, RR `86290005`/`9279-1`, SpO₂ `103228002`/`59408-5`, HR `364075005`/`8867-4`, Temp `276885007`/`8310-5`, plus `UKCore-Flag` + SBAR). Day-1 zero-EPR interoperability for paramedics, 111 & **DTAC v2.0** (Apr 2026) trusts.
- **Hardware & EI:** Pure Python (`zlib`, `segno`/`qrcode` SVG, `sqlite3` hash chain, `/api/fhir` & `/api/audit`) beside `.eim` runners.
- **Verified Standards (HTTP 200):** [FHIR UK Core R4](https://simplifier.net/hl7fhirukcorer4); [SMART Health Cards](https://spec.smarthealth.cards/) (**CC BY 4.0**).
- **Demo / Risks / Effort:** Cut WAN live—all models keep inferring and a judge scans the UNO Q QR to read structured FHIR UK Core R4 + SBAR offline. *Risks:* keep QR ≤Version 20 (~800 B compressed) + LAN URL for verbose JSON. **2 h (Sun)** | **Roadmap:** ES256 **SMART Health Links** + HL7 IPS + EPR push.

### S6. Clinical Wedge Pack: Chemo CG151 + Care-Home RESTORE2 & Martha's Rule
- **What / Who / Why:** **Pathway Profile Selector** for two fundable NHS wedges: (1) **Chemo 7–14 d Neutropenic Nadir** (10–50% incidence; finite window solves wear fatigue) w/ hard **NICE CG151/NG253** bypass (oral temp `≥38.0 °C` → immediate UKONS 24 h hotline / 1 h IV antibiotics, never delayed by AI); (2) **Care-Home RESTORE2** (Soft Signs + 4AT + SBARD); (3) universal one-tap **Martha's Rule** *"Something feels wrong"* override (**4,906 NHS calls → 241 potentially life-saving interventions, 93 ICU admissions**, Sep 2025 NHS eval) emitting `UKCore-Flag`. Proves NHS literacy (**NICE NG253** pub. **19 Nov 2025**) against Isansys's Jun 2025 liquidation & Best Buy's Jun 2025 Current Health divestment.
- **Hardware & EI:** Deterministic mode layer in `main.py` & `dashboard.html` feeding `build_escalation()` + S5 `UKCore-Flag`, grounded in `TIHM`.
- **Verified Sources (HTTP 200):** [NICE NG253](https://www.nice.org.uk/guidance/ng253) (19 Nov 2025); [NICE CG151](https://www.nice.org.uk/guidance/cg151); [TIHM](https://zenodo.org/records/7622128) (**CC BY 4.0**, 7 MB).
- **Demo / Risks / Effort:** Entering `38.1 °C` in *Chemo Nadir*—or tapping *Martha's Rule* with normal vitals—instantly overrides low AI scores with a CG151/carer SBARD alert. *Risks:* never feed wrist skin temp into CG151 `>38 °C`. **1.5 h (Sun)** | **Roadmap:** 1:10 care-home hub, Postpartum **NG255/MEWS** (+£20 BLE BP cuff), 90-day post-sepsis loaner.

### S7. Zero-Hardware Perfusion & Autonomic Fusion (Watch 8 Unlocked + Nailbed CRT)
- **What / Who / Why:** Extracts circulatory signals from existing hardware to mitigate missing BP: (1) fix `main.py:54` to ingest `ibi_ms` & `ambient_c` already sent by `Vitals.kt:49` → live resting **RMSSD** ([Ahmad 2009](https://doi.org/10.1371/journal.pone.0006642)); (2) **Passive Stand Orthostatic ΔHR** (chest tilt + Watch HR surge `≥30 bpm` = 98% specific volume-loss rule-in, [McGee *JAMA* 1999](https://doi.org/10.1001/jama.281.11.1022); passive/supervised only); (3) **Nailbed Camera CRT** (10 s blanch-release green-channel exponential $\tau$, **ANDROMEDA-SHOCK** [*JAMA* 2019](https://doi.org/10.1001/jama.2019.0071)/2025 & [Blaxter 2016](https://doi.org/10.1088/0967-3334/37/1/83), far less melanin-biased than knee mottling; run on **laptop `localhost:8000`** or **Android Chrome HTTPS**, NOT plain HTTP LAN or iOS Safari torch); (4) Roadmap Watch 8 `.aar`: `PPG_CONTINUOUS` (25 Hz raw G/R/IR fixed-optics PI), `EDA_CONTINUOUS` (1 Hz sweat), `ECG_ON_DEMAND` (`ECG_MV + PPG_GREEN` PAT/AFib). Zero-BOM circulatory depth.
- **Hardware & EI:** Unblock `ibi_ms`/`ambient_c` + RMSSD + passive-stand in `main.py`; JS green-channel CRT on `localhost`; optional EI `Spectral Analysis` PPG quality gate.
- **Verified Data (HTTP 200):** [BIDMC v1.0.0](https://physionet.org/content/bidmc/1.0.0/) (**ODC-By 1.0**); [MMASH v1.0.0](https://physionet.org/content/mmash/1.0.0/) (**ODbL 1.0**); [VitalDB v1.0.0](https://physionet.org/content/vitaldb/1.0.0/) (**CC BY 4.0**).
- **Demo / Risks / Effort:** Watch streams RMSSD; volunteer presses fingernail to localhost/Android camera for 3 s—plotting `CRT = 1.6 s (Normal)` onto SBAR. *Risks:* phone AE/AWB corrupts raw flash PI (use normalized CRT $\tau$); stand test is 22% sensitive (rule-in only). **2 h (Sun: 45 min IBI/stand + 75 min CRT)** | **Roadmap:** Watch 8 `PPG_CONTINUOUS`/`EDA_CONTINUOUS`/`ECG_ON_DEMAND` + API 36 permissions.

### S8. Multi-Task Voice & Respiratory Audio Suite (4AT Digits + EI Performance Calibration + SBCT)
- **What / Who / Why:** Upgrades `training/speech_kws.py` into a neuro-respiratory screen: (1) finishes **4AT-inspired digits-backwards** (`attention.py` → NEWS2 "C"); (2) runs **EI Performance Calibration** (Free plan, ≤30 min synthetic stream) for an audited **FAR vs FRR curve**; (3) reuses `digits.eim` for a **Single-Breath Count Test (SBCT)** breathlessness trend ([Ali 2011](https://pubmed.ncbi.nlm.nih.gov/21226686/), $r=0.71$ vs FVC; rejecting Roth-score hypoxia claims per [Greenhalgh *BMJ* 2020](https://doi.org/10.1136/bmj.m1431)); (4) roadmap `Audio (MFE)` cough check. One `int8` audio `.eim` delivers cognition + breathing reserve + EI Performance Calibration rigor.
- **Hardware & EI:** EI Project #3 (`Audio 16 kHz` → `Audio (MFCC)` → `Classification`) + **Performance Calibration** → `digits.eim` + `POST /attention/score` + SBCT. Roadmap Project #4: `Audio (MFE)` on Coswara/ESL-EPFL.
- **Verified Data (HTTP 200):** [Speech Commands v2](https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz) (**CC BY 4.0**, [arXiv:1804.03209](https://arxiv.org/abs/1804.03209)); [Coswara](https://zenodo.org/records/7188627) (**CC BY 4.0**); [ESL-EPFL Cough](https://zenodo.org/records/7562332) (**CC BY 4.0**); [SPRSound](https://github.com/SJTU-YONGFU-RESEARCH-GRP/SPRSound) (**CC BY 4.0**).
- **Demo / Risks / Effort:** Prompt `"Say 7-2-9-4 backwards"` clears locally in <1 s; scrambling digits triggers NEWS2 "C" and Carer SBAR. *Risks:* room noise (mitigate w/ Performance Calibration + `sequences.npz` fallback). **2 h (Sun)** | **Roadmap:** `Audio (MFE)` cough/wheeze + speaking-rate baseline.

---

## 4. Three Moonshots (Startup / Paper Horizon)

1. **"SepsisHome-1000" Biobank & MHRA AI Airlock Twin:** Close the global evidence void (zero public home-wearable-to-sepsis cohort) via a 1,000-patient NHS Oncology/Frailty shadow-mode trial linking wearables + FHIR to **MC-MED** transfer, **BioGears** counterfactual twins, and an **MHRA AI Airlock Phase 3** (Oct 2026) post-market drift loop—building the first UKCA/FDA De Novo pre-hospital sepsis dossier beyond inpatient-only **Prenosis DEN230036** and **Bayesian TREWS K250680**.
2. **Cuffless Distributive-Shock & Capillary-Leak Sensing + Silicon MLC:** Fuse three verified capabilities already in our Watch 8 `.aar` + LSM6DSOX: simultaneous `ECG_MV + PPG_GREEN` **Pulse Arrival Time** (vasoplegia), Watch 8-exclusive **`MF_BIA_ON_DEMAND`** 5–250 kHz **phase angle** (capillary-leak ECW/TBW), and LSM6DSOX **15 µA on-chip MLC** (6-axis rigors + GCG).
3. **£30 BOM Federated, Skin-Tone-Equitable Sentinel for Care Homes & LMICs:** Swap the £319 Watch 8 for a £15 washable chest strap + £15 clip oximeter feeding one £60 offline UNO Q per **10-bed care-home wing** or **rural LMIC clinic** (zero SIM/cloud), combining federated baseline adaptation (zero raw Art. 9 PHI leaves site) with **BOLD**/OpenOximetry MST/ITA calibration to narrow **MBRRACE-UK's 2.72× Black maternal disparity** and the **85% LMIC share of 11M sepsis deaths**.

---

## 5. Recommended 13-Hour Package (Sat 21:00 → Sun 12:00 UK)

**Team:** 2 Humans (**H1** Hardware/Watch/Demo, **H2** EI Studio/Clinical/Pitch) + **3 AI Coding Agents** (**A1** ML/Data, **A2** Board/UI/Interop, **A3** Firmware/EI).

| Window (UK) | Parallel Workstreams (Ordered by Impact) | Exit Gate |
|---|---|---|
| **21:00–23:30** *(2.5 h)* | **A1 (S1+S4):** Fix `train_gbm.py:46` + `features.py` (personal z-score/CUSUM, `HR/Temp`, `PRQ`, `ROX`, `Age`); run `strict_eval.py`, Age/Sex audit & `eICU-Demo`; export `sepsis_v2.eim`.<br>**A2 (S7a+S5+S6):** Fix `main.py:54` (`ibi_ms`, `ambient_c`) + RMSSD; add CG151/RESTORE2/Martha's Rule + FHIR UK Core R4 + SHC QR + SHA-256 audit.<br>**H1+A3 (S2+S8):** Enable gyro (`0x22`), record 2 min/class (`still`/`moving`/`shiver`); finish `digits.eim` + **Performance Calibration** & **Data Explorer**. | `sepsis_v2.eim` beats NEWS2 & closes ≥75 cliff; IBI flows; QR scans offline; `digits.eim` + IMU trained. |
| **23:30–02:00** *(2.5 h)* | **A3+H1 (S2):** Dual-block IMU (`Classification` + **GMM Anomaly**) + **EON Tuner**; 90-min timebox to flash INT8 EI C++ onto **STM32U585** (else `motion.eim` on QRB2210).<br>**A1+A2 (S3+S4):** Ship **Home-Reality Stress-Test Lab** (6 toggles on PhysioNet + BioGears CSV) + Equity Model Card & 93–96% SpO₂ guard.<br>**H2 (S8):** Wire `digits.eim` 4AT + SBCT; test WAN pull. | All 3 EI models run live offline on UNO Q; Stress-Test Lab + 4AT live. |
| **02:00–03:30** *(1.5 h)* | **A2+H1 (S7b stretch):** Passive-stand `ΔHR` + localhost nailbed CRT card. **Code freeze 03:30** *(rest split 02:30–08:30)*. | Frozen build; offline smoke test green. |
| **08:30–11:30** *(3.0 h)* | **H1+H2:** Full live rehearsal (WAN pull, walk/shiver/digits, Stress-Test toggles, QR scan), record **3-min backup video**, 5-slide deck (EON Tuner, Perf Cal, Fairness Audit, Market Autopsy). | Bulletproof live demo + backup video by 11:30. |

### 3-Minute Pitch Transformation
- **Before:** *"LightGBM ICU replay + partial NEWS2 with fewer separate alarms (more alarm hours) and an SBAR card."*
- **After:** **0:00–0:35** Hospital sepsis AI just won FDA clearance & CMS payment (`DEN230036`, `K250680` Oct 2026) while proprietary cloud RPM failed (Isansys CVL, Current Health divestment, Jun 2025)—leaving **7–14 d chemo nadir (CG151)** and **care homes (RESTORE2)** exposed. **0:35–1:25** Cut internet live: UNO Q (`QRB2210` + `STM32U585`) + Watch 8 runs **3 heterogeneous EI models offline** (walk gated, shiver flagged, digits-backwards fumble → NEWS2 "C" + SBAR). **1:25–2:20** Toggle *"Dark skin +3% SpO₂ + Beta-blocker + 15-min walk"* in our Digital Twin Lab—NEWS2 fails while our personalized, skin-tone-invariant sentinel holds; show our **Fairness Audit** (fixing our −12.9 pp ≥75 cliff) & `eICU-Demo` win. **2:20–3:00** Tap *Martha's Rule* → judge scans offline **FHIR UK Core R4 + SBAR QR** (SHA-256 **DCB0129** logged); close on £30 BOM scaling to NHS Virtual Wards & LMICs.

---

## 6. Unverified Items (Plain Disclosure)
- **OpenOximetry direct URL:** `openoximetry.org` returned HTTP 403 and guessed PhysioNet slugs 404; **BOLD v1.0** (`https://physionet.org/content/blood-gas-oximetry/1.0/`, Credentialed 1.5.0) was live-verified HTTP 200 instead.
- **Qualcomm–Arduino closing date:** 7 Oct 2025 announcement verified; formal regulatory closing date unverified.
- **STM32U585 Zephyr C++ EI build w/ our `sketch.ino`/`Bridge`:** Officially documented by Edge Impulse, not compile-tested on this board (90-min timebox + Linux `.eim` fallback).
- **Watch 8 runtime `EDA_CONTINUOUS` / `MF_BIA_ON_DEMAND`:** Verified in bundled `.aar` & SDK 1.4.1 notes, not runtime-tested on physical Watch 8 (`supportHealthTrackerTypes` + API 36 permissions).
- **Board RAM (2 GB vs 4 GB):** Not probed via `free -h`; assumes 2 GB worst-case (keeping SLMs off Sunday).
