# Hardware-First Sensor & Edge-AI Ideas (`neon_v3`)

*Grounded in `board/`, `wearos/`, and `javap` of `samsung-health-sensor-api-1.4.1.aar` (`ECG_ON_DEMAND`, `MF_BIA_ON_DEMAND`, `PPG_CONTINUOUS`, `EDA_CONTINUOUS`). Assumes Modulino Thermo/Light/Vibro stay unreliable; uses UNO Q (QRB2210 + STM32U585 + 8×13 LED matrix), LSM6DSOX chest IMU, Watch 8, S26 Ultra. Ranked by **stage wow × 8 h feasibility**.*

---

### 1. Optical Nailbed Capillary Refill Time (CRT) — ANDROMEDA-SHOCK at Home *(3.0 h)*
- **Sensors:** S26 Ultra rear camera + white torch (or UNO Q USB webcam).
- **EI model:** `Image` (MobileNetV2) or 1D-CNN on nailbed green/red trace (`.eim`) classifying `no_nail`/`blanching`/`refilling`/`perfused` to lock release $t_0$ and reject slip before fitting $\tau$.
- **Data:** 45 min team capture (warm normal, ice-chilled slow refill, slip/lighting negatives). No large public smartphone nailbed-CRT video dataset exists.
- **Sepsis link:** Prolonged CRT (>3 s) is a landmark shock resuscitation target (ANDROMEDA-SHOCK, *JAMA* 2019/2025) and far less melanin-biased than mottling or SpO₂.
- **30 s demo:** Press fingernail 5 s under camera/torch, release—live refill curve (`CRT ~1.4 s`). Chill finger in ice 15 s, repeat—curve visibly flattens (`>2.5 s`).
- **Risk:** Phone AE/AWB drift and plain-HTTP camera block; normalize green/red against adjacent skin and serve via USB cam, laptop `localhost`, or HTTPS.
- **Limitation:** Cold slows refill without sepsis; uncalibrated against glass-slide CRT or lactate.

### 2. Single-Clock Cuffless Pulse Arrival Time (PAT) & Sepsis-AFib Screen *(3.5 h)*
- **Sensors:** Watch 8 `ECG_ON_DEMAND` (`ValueKey$EcgSet`: `ECG_MV` + simultaneous `PPG_GREEN` on one clock), UNO Q.
- **EI model:** `Raw Data`/`Spectral Analysis` → 1D-CNN `.eim` classifying 10 s ECG (`sinus`/`afib_irregular`/`artifact`), paired with beat-by-beat R-peak-to-PPG-foot PAT (ms).
- **Data:** **PhysioNet/CinC 2017 AFib** (ODC-By 1.0), **VitalDB** (CC BY 4.0, paired ECG+PPG), + 30 min Watch capture (rest, arm raised, loose contact).
- **Sepsis link:** Tackles wearables' #1 gap—no BP cuff for vasoplegic shock (PAT shifts with vascular tone)—plus screens sepsis-triggered AFib.
- **30 s demo:** Touch crown 15 s at rest—live ECG+PPG and `PAT` (`Sinus`). Raise arm overhead (hydrostatic BP drop), repeat—PAT shifts live; lift finger to fire `artifact`.
- **Risk:** Foreground-only (~30 s, excludes SpO₂) and Dev Mode gating; probe `supportHealthTrackerTypes` first.
- **Limitation:** Relative intra-person proxy, not mmHg; arm elevation shows hemodynamics, not shock.

### 3. Autonomous STM32U585 Edge Impulse + 8×13 Chest LED Beacon *(3.5 h)*
- **Sensors:** Chest LSM6DSOX (gyro `0x22`, 52 Hz), UNO Q **STM32U585**, **hard-wired 8×13 LED matrix** (`ArduinoGraphics` in `sketch.yaml`) + RGB LEDs.
- **EI model:** 6-axis `Spectral Analysis` → INT8 `Classification` + `K-means Anomaly` as an **Arduino/Zephyr C++ library** on STM32U585 (stretch: LSM6DSOX 15 µA MLC wake tree).
- **Data:** **PAMAP2** chest IMU (CC BY 4.0) + 45 min capture (`still`, `walking`, `rigor_like`, `strap_off`).
- **Sepsis link:** Keeps chest gating and a dark-room visual triage beacon (`RR` + flashing `SOS`) alive if Linux, Wi-Fi, and flaky Vibro all die.
- **30 s demo:** Chest UNO Q animates live breath wave + `RR` on 8×13 matrix. Cut Wi-Fi **and kill Linux Python**—STM32U585 EI C++ keeps gating walking and latches a pulsing alert.
- **Risk:** Zephyr C++/RAM friction; enforce 90-min timebox (fallback: STM32 matrix+DSP with Linux `motion.eim`).
- **Limitation:** Visual-only beacon cannot wake a sleeper without working haptics; board is bulky on chest.

### 4. "Cold-Clammy Shock Triad" — Vasoconstriction & Diaphoresis Fusion *(3.5 h)*
- **Sensors:** Watch 8 `PPG_CONTINUOUS` (25 Hz raw G/R/IR), `EDA_CONTINUOUS` (`SKIN_CONDUCTANCE`), `SKIN_TEMPERATURE_CONTINUOUS` (`OBJECT−AMBIENT`), `IBI_LIST` RMSSD.
- **EI model:** `Spectral Analysis` + `Classification` + `K-means Anomaly` `.eim` on 10 s PPG amplitude, EDA slope, `T_skin−T_amb` (`perfused`, `vasoconstricted_surge`, `motion_artifact`).
- **Data:** 1 h capture (rest, contralateral cold-pressor, walking); **PhysioNet BIDMC** (ODC-By 1.0) & **MMASH** (ODbL 1.0).
- **Sepsis link:** Early shock drives sympathetic surge: vasoconstriction shrinks PPG perfusion and `T_skin−T_amb`, sweat spikes EDA, HRV drops.
- **30 s demo:** Dry Watch on left wrist shows warm PPG + flat EDA. Dip *right* hand into ice water 15 s (systemic reflex)—PPG shrinks, EDA climbs, skin cools, EI flips to `Vasoconstriction/Surge`.
- **Risk:** `EDA_CONTINUOUS` Dev Mode gating and PPG AGC jumps; normalize AC/DC, fallback to PPG + `T_skin−T_amb` + RMSSD.
- **Limitation:** Cold, pain, or anxiety causes the same reflex; non-specific distress cue, not diagnostic.

### 5. Multi-Frequency Bioimpedance (5–250 kHz) Capillary-Leak Scanner *(3.0 h)*
- **Sensors:** Watch 8 `MF_BIA_ON_DEMAND` (`ValueKey$MfBiaSet`: magnitude/phase at 5, 10, 50, 250 kHz; fallback `BIA_ON_DEMAND` 50 kHz `BODY_IMPEDANCE_DEGREE`).
- **EI model:** `Raw Data` → `K-means/GMM Anomaly` `.eim` scoring `[|Z|_5k..250k, φ_5k..250k, Z_5k/Z_250k]` against personal baseline.
- **Data:** 30 min capture (baseline, posture shifts, poor contact). No public wearable sepsis-BIA dataset exists.
- **Sepsis link:** Capillary leak expands extracellular water (`Z_5k/Z_250k`) and depresses 50 kHz **Phase Angle**, a known ICU mortality predictor.
- **30 s demo:** Touch Watch buttons 15 s—live 4-frequency Cole-Cole arc and Phase Angle plot on UNO Q, overlaid with labelled simulated leak drift firing the anomaly flag.
- **Risk:** `MF_BIA_ON_DEMAND` regional/Dev Mode gating and arm-torso contact noise; probe minute 0.
- **Limitation:** Upper-body BIA shifts with hydration/posture, lacks home-sepsis validation, cannot be provoked live.

### 6. 208 Hz Sternum SCG/GCG Watch-Free Pulse & Bilateral Rigors *(4.5 h)*
- **Sensors:** Chest LSM6DSOX (208 Hz 6-axis FIFO) + Watch 8 `ACCELEROMETER_CONTINUOUS`.
- **EI model:** 6-axis `Spectral Analysis` (5–35 Hz cardiac + 4–12 Hz rigor) → Keras `.eim` (`cardiac_still`, `systemic_rigor_like`, `unilateral_arm`, `walking`).
- **Data:** **PhysioNet CEBS** (ODC-By 1.0, sternal SCG+ECG+resp) + 45 min paired chest+wrist capture.
- **Sepsis link:** Sternal SCG/GCG provides watch-free mechanical HR backup while charging; chest+wrist coherence rejects one-arm gestures from bacteraemic rigors.
- **30 s demo:** Remove Watch—sternum IMU tracks mechanical heartbeat + 6-axis breathing. Wave one arm (`Ignored: unilateral`), then shiver torso+arms (`Bilateral rigor-like`).
- **Risk:** Loose strap damps vibrations; 208 Hz Bridge bandwidth (compute envelope on STM32 if needed).
- **Limitation:** Acted shivering ≠ clinical rigors; SCG requires tight sternal coupling and stillness.

### 7. Inaudible 19 kHz Ultrasonic Chest Sonar *(4.0 h)*
- **Sensors:** S26 Ultra or laptop speaker (19 kHz CW, 48 kHz Fs) + mic.
- **EI model:** I/Q phase-demodulated chest displacement (mm) → `Spectral Analysis` + Keras `.eim` (`normal_breath`, `tachypnea`, `apnea_pause`, `artifact`).
- **Data:** 45 min capture at 0.3–0.8 m (normal, fast, breath-hold, bystander motion).
- **Sepsis link:** Contactless, dark-room, skin-tone-invariant RR backup when straps come off overnight.
- **30 s demo:** Aim device 0.5 m from chest—inaudible sonar plots live breathing, catches a 10 s breath-hold (`Apnea`), and tracks rapid breaths with zero wearables.
- **Risk:** Speaker/mic roll-off >18 kHz and stage multipath from nearby movement.
- **Limitation:** Fails with multiple moving bodies or >1 m range; sensitive to audio AGC.

---

## Recommended Build Order (< 7.5 h Parallelized)

1. **0:00–0:20 (Gate):** Log Watch 8 `supportHealthTrackerTypes` (`ECG_ON_DEMAND`, `PPG_CONTINUOUS`, `EDA_CONTINUOUS`, `MF_BIA_ON_DEMAND`); verify UNO Q 8×13 matrix + LSM6DSOX gyro `0x22`.
2. **0:20–3:30 (Core WOW, parallel):** **Track A (#3, 3.5 h):** 52 Hz 6-axis LSM6DSOX + 8×13 matrix breath/alert beacon + 90-min timebox for STM32U585 EI C++ (live Linux-kill demo). **Track B (#1, 3.0 h):** Optical Nailbed CRT + EI blanch/refill `.eim` + ice-finger shift.
3. **3:30–7:00 (Watch 8 BioActive, gated):** **Track A (#2, 3.5 h):** Single-Clock ECG+PPG PAT + EI sinus/AFib/artifact `.eim`. **Track B (#4 or #5, 3.0–3.5 h):** Cold-Clammy Triad (PPG+EDA) or 4-Freq BIA (`MF_BIA_ON_DEMAND`).
4. **7:00–7:30:** Freeze, rehearse four live provocations (ice nailbed CRT, arm-raise PAT, contralateral ice-cup vasoconstriction, live Linux kill on chest matrix), record backups.
