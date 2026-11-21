# Sepsis Early-Warning Wearable — Hackathon Brainstorm (~15h Left)

Ideas ranked by **impact vs. effort** for a Sunday 12:00 UK deadline, optimised for medtech judging: clear clinical value, deep Edge Impulse usage, and a rock-solid, honest on-device demo.

---

## 1. Edge Impulse: Higher-Impact Architecture

Right now, Edge Impulse only classifies slow hourly ICU vitals, while the live 25 Hz chest IMU uses hand-rolled autocorrelation. Splitting into a **two-impulse edge architecture** turns this into a standout Edge Impulse submission.

1. **High Impact / ~2.5h — On-Device Chest IMU Impulse (Activity Gating + Rigors + Falls):**
   - **Blocks:** `Spectral Analysis` DSP (2–4 s sliding windows at 25 Hz; captures 0.2–0.5 Hz breathing, 1–3 Hz gait, and 4–8 Hz shivering) → `Classification (Keras)` NN + `EON Tuner` for latency/RAM profiling.
   - **Classes:** `resting_still`, `walking_active`, `rigors_shivering` (classic early bacteraemia sign), and `fall_or_collapse`.
   - **Why it wins:** Autocorrelation RR breaks during movement, and walking elevates HR/RR—causing false NEWS2 alerts. Use the IMU model to **gate RR extraction** (only compute RR when `resting_still`) and suppress exercise-induced tachycardia alerts, while immediately escalating risk on `rigors_shivering` or `fall_or_collapse`.
   - **Data:** Record 2–3 min per class on your actual LSM6DSOX (plus PAMAP2 chest data for `walking`/`resting`). Label rigors honestly as simulated proof-of-concept data.

2. **High Impact / ~2.5h — BYOM LightGBM / XGBoost on Trajectory Features (PhysioNet 2019):**
   - **Why AUC is stuck at 0.698:** Small dense nets on raw 8×4 hourly grids miss slopes, volatility, and cross-vital ratios. Gradient-boosted trees dominate PhysioNet 2019 tabular vitals.
   - **Features on 8–12 h windows:** per-vital slopes (`dHR/dt`, `dResp/dt`, `dTemp/dt`), min/max/SD, delta from window baseline (`HR - HR_t0`), and perfusion/stress ratios (`HR / O2Sat`, `HR × Resp`). Keep strict patient-level splits and **exclude `ICULOS`** to prevent leakage.
   - **Deploy:** Export LightGBM/XGBoost via Edge Impulse **BYOM** (or ONNX → `.eim` runner on the UNO Q Linux MPU). Expect a realistic jump toward ~0.75–0.79 ROC-AUC on 4 vitals, plus explainable top-contributing features for the dashboard.

3. **Medium-High Impact / ~1.5h — Unsupervised `Anomaly Detection (GMM)` for Patient Drift:**
   - Train Edge Impulse's **Gaussian Mixture Model (GMM)** anomaly block on healthy/baseline vitals (or resting IMU features).
   - **Clinical story:** Chemo and post-op patients often drift from *personal baseline* before crossing fixed NEWS2 thresholds. GMM adds an out-of-distribution safety score without needing sepsis labels.

4. **Low Effort / ~30m — EON Tuner Proof Slide:**
   - Run EON Tuner on the IMU impulse to quote exact inference latency, RAM, and flash numbers on STM32 vs. UNO Q Linux, proving offline edge efficiency.

---

## 2. Public Datasets (Verified)

| Dataset | URL | Access / Licence | Size & Utility |
|---|---|---|---|
| **PhysioNet/CinC Challenge 2019** (Early Sepsis) | https://physionet.org/content/challenge-2019/1.0.0/ | Open (CC BY 4.0) | ~42 MB zip, 40,336 ICU patients. Best for BYOM LightGBM + honest held-out patient replay. |
| **MIMIC-IV Clinical Database Demo** | https://physionet.org/content/mimic-iv-demo/ | Open (ODbL 1.0, no credentialing) | ~15.5 MB, 100 patients. Fast sanity-check on hospital/ICU vitals. *(Full MIMIC-IV / MIMIC-IV-ED requires CITI + PhysioNet Credentialed Health Data License 1.5.0—skip tonight.)* |
| **PAMAP2 Physical Activity** | https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring | Open (CC BY 4.0) | ~656 MB zip, 9 subjects, **100 Hz chest IMU** (downsample to 25 Hz for posture/activity gating). |
| **WESAD** | https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html (UCI DOI `10.24432/C57K5T`) | Academic / non-commercial | ~2.5 GB zip, 15 subjects, **chest RespiBAN** (accel, resp, temp) + **wrist E4** (BVP, temp, accel). Mirrors your exact chest+wrist setup. |
| **PPG-DaLiA** | https://archive.ics.uci.edu/dataset/495/ppg+dalia | Open on UCI (CC BY 4.0; originally academic) | ~2.7 GB, 15 subjects, chest+wrist IMU + PPG for motion-artifact gating. |
| **BIDMC PPG & Respiration** | https://physionet.org/content/bidmc/1.0.0/ | Open (ODC-By 1.0) | ~218 MB, 53 ICU patients (PPG, HR, RR, SpO2). Useful if validating PPG-derived RR. |
| **VitalDB** | https://physionet.org/content/vitaldb/1.0.0/ | Open (CC BY 4.0) | ~95.4 GB total (6,388 surgical cases; fetch individual cases via API). Post-surgical vitals + BP/PPG proxies. |
| **SisFall** | http://sistemic.udea.edu.co/en/investigacion/proyectos/english-falls/ | Academic (HF mirror CC BY 4.0) | ~232 MB, 38 subjects, 19 ADLs + 15 fall types (waist IMU) for fall pretraining. |
| **CEBS Database** | https://physionet.org/content/cebsdb/1.0.0/ | Open (ODC-By 1.0) | ~1.6 GB zip, 20 subjects, chest seismocardiogram/accel + breathing. |
| **COUGHVID** | https://doi.org/10.5281/zenodo.7024894 | Open (CC BY 4.0) | ~951 MB zip, >20k cough audio clips (only relevant if adding a mic—skip tonight). |

*Note: No clean open chest-IMU dataset for clinical rigors/shivering was verified; collect acted rigors on your LSM6DSOX and disclose it transparently.*

---

## 3. Other Sensors & Closing the NEWS2 Gap

**Use what you already have first (zero procurement):**
- **Modulino Thermo (ambient temp/humidity):** Wrist skin temperature drops in cold rooms or during septic peripheral vasoconstriction. Log `T_skin - T_ambient` to flag abnormal peripheral cooling vs. room-temperature drift.
- **Modulino Vibro:** Closed-loop patient prompting ("sit still 30 s for SpO2/RR check" or alert acknowledgement).
- **Software ACVPU ("Confusion" in NEWS2) — zero hardware:** When risk rises, buzz Vibro and pop a 10-second one-tap cognitive prompt on the Galaxy Watch or dashboard ("Tap the green circle / confirm you feel clear-headed"). Missed or wrong response adds the missing **NEWS2 +3 new-confusion score**. Clinicians will immediately notice this.

**Cheap Qwiic/I2C add-ons (only if already in a hackathon bin; otherwise pitch as v2 BOM):**
- **MLX90614 / MLX90632 IR Temp (~£12):** Better core-proxy temp; combined with wrist temp gives **core-to-peripheral gradient** (shock/vasoconstriction proxy).
- **MAX30101 / MAX32664 Pulse Oximeter (~£20–35):** Continuous SpO2 + **Perfusion Index (PPG AC/DC)** for peripheral shutdown, and pulse-transit-time BP trends when paired with chest SCG.
- **AS7341 / VEML6040 Colour Sensor + FSR (~£15):** Roadmap concept for optical **capillary refill time (CRT)** and skin mottling.

---

## 4. Honest Demo & Pitch Wow Factors

1. **Live "Activity-Gated" Contrast (60 s):** Jog in place wearing the chest IMU + Watch → dashboard shows `Walking` (EI IMU model), pauses RR autocorrelation, and suppresses false HR alarms. Sit still → clean ~18/min RR returns. Simulate shivering → IMU model triggers `Rigors` in <1 s, Vibro buzzes, and the ACVPU Watch check fires.
2. **Labelled PhysioNet Clinical Replay (45 s):** Add a prominent **"Validation Replay — Held-Out PhysioNet Sepsis Case"** toggle. Scrub through an actual patient's 12 hours pre-onset showing plain NEWS2 staying low while your BYOM LightGBM + GMM anomaly curve rises hours earlier, alongside a **"Why Flagged"** bar (e.g., `HR slope +14 bpm/4h`, `RR trend +4/min`).
3. **Offline Edge Moment (15 s):** Show inference running locally on the UNO Q with no cloud API calls (or local hotspot only)—crucial for patient privacy and patchy home Wi-Fi in NHS virtual wards.
4. **Credible Clinical Framing:** Position as a **virtual-ward triage nudge** bridging the 4–6 h NEWS2 blind spot, never a standalone sepsis diagnosis. Report sensitivity at fixed false-alarm rate (e.g., alerts/patient-day), not just ROC-AUC.

---

## 5. Risks & Things to Cut

- **Cut now:** MIMIC-IV credentialing, new unowned I2C sensors, deep sequence models on hourly vitals, BLE GATT rewrites (keep Watch JSON POST), and **Modulino Light** (weak clinical payoff).
- **Time-box I2C debugging to 45 min:** Check Qwiic daisy-chain cables/addresses for Vibro and Thermo; if Thermo stays stubborn, keep Movement + Vibro and move on.
- **Venue Wi-Fi risk:** Run a dedicated phone hotspot for UNO Q + Watch, cache the last Watch JSON payload, and keep Replay Mode one click away.
- **Leakage trap:** Double-check PhysioNet preprocessing—no `ICULOS`, no forward-looking imputation, patient-disjoint train/val/test splits.

---

## Top 5 Recommendations (Priority Order)

1. **Build the 25 Hz chest IMU Edge Impulse model** (`Spectral Analysis` + NN + EON Tuner) for `still / walking / rigors / fall` to gate RR/HR false alarms and create a live high-frequency edge demo.
2. **Upgrade the sepsis model via Edge Impulse BYOM LightGBM** using engineered slopes, variability, and cross-vital ratios on 8–12 h PhysioNet 2019 windows, plus simple feature-reason explanations on the dashboard.
3. **Add the labelled PhysioNet Trajectory Replay mode** comparing NEWS2 vs. your BYOM + GMM anomaly score hour-by-hour on a real held-out sepsis patient.
4. **Close the NEWS2 "Confusion" gap in software** with a Vibro-triggered 10-second ACVPU tap check on the Watch/dashboard (and time-box fixing Modulino Vibro + Thermo on I2C to 45 min).
5. **Add an Edge Impulse GMM Anomaly Detection block** to capture patient-specific baseline drift—strengthening both clinical credibility and Edge Impulse platform depth.
