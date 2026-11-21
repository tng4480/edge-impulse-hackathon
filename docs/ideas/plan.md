# Level-up plan (merged from Claude, Gemini 4 Neon, GPT 6.2 Sol)

## Status, Saturday about 18:00

- DONE #1: LightGBM 24 h trends, in Edge Impulse via BYOM (impulse #4, ONNX of the trees because the free plan blocks classical ML), with an aarch64 `.eim` built and checked against LightGBM. Results are in [../results.md](../results.md).
- DONE #2 (engine): `replay.py` + `replay_cases.json`. Dashboard and endpoints were handed to the board thread.
- READY #3: `model_runner.py` (eim runner + identical pure-Python fallback), not yet run on the board, which is offline.
- READY #4: `training/motion.py` (record, setup, train). Needs the board back, the board thread's `/api/imu/raw`, and a **second Edge Impulse project** (impulses in one project share a dataset).
- Board thread owns #5 (check-in panel) and #6 (Thermo gradient).

Sources: [gemini.md](gemini.md), [gpt.md](gpt.md), plus Claude's LightGBM experiment (`training/gbm_experiment.py`).
Written Saturday about 17:30. Deadline Sunday 12:00.

## What all three agree on

1. **Two Edge Impulse models, not one.** Keep the sepsis-risk model on hourly vitals, and add a second impulse on the 25 Hz chest IMU (Spectral Analysis + Classification) that tells `still` from `moving`. It pauses the breathing estimate during movement and suppresses exercise-driven HR and RR alarms. Optionally it also flags `shiver-like motion` (rigors) and falls. This is the live, high-frequency Edge Impulse demo.
2. **A labelled replay of a real held-out PhysioNet sepsis patient.** It plays hour by hour with plain NEWS2 next to the model score, so judges see the model rise before NEWS2 does. It must be labelled "Recorded ICU case · accelerated".
3. **Gradient-boosted trees beat the dense network.** Deploy one through Edge Impulse BYOM (LightGBM and XGBoost are supported).
4. **Close the NEWS2 gaps honestly.** Add a confusion check and manual entries for blood pressure and confusion. Label skin temperature as skin and SpO2 as a spot reading, and show the age of each reading.
5. **Cut** falls (unless trivial), audio and cough, cuffless BP, camera mottling, MIMIC credentialing and new I2C debugging beyond a 45-minute time box.

## New evidence: LightGBM experiment (done)

Same patient split, same labels, 24 h windows, trend features (last, mean, min, max, std, 1 h and 6 h change, slope per vital):

| Model | Test ROC AUC | Sepsis caught at 15 % false alarms |
|---|---|---|
| NEWS2 (4 vitals) | 0.642 | 34 % (score 5+ or any 3) |
| Current dense net, 8 h raw | 0.698 | 38 % |
| **LightGBM, 24 h trends, wearable vitals only** | **0.745** | **46 %** |
| + age | 0.747 | 46 % |
| + hours in ICU | 0.839 | 66 % (NOT usable: a known confound in this dataset; a home patient has no ICU clock) |

The test sets differ slightly between the rows: same patients, different window sampling. Re-run all three on identical windows before quoting the numbers in the pitch.

## Where they disagree, and the call

- **What comes first.** GPT puts the existing model running on the board first, and Gemini puts the IMU model first. **Call:** the hardware is disconnected right now, so start with the work that needs no board (LightGBM through BYOM, the replay engine, the check-in UI, IMU data prep from PAMAP2). Do the on-board `.eim` and live IMU recording as soon as it is back.
- **Anomaly detection.** Gemini suggests a GMM baseline-drift block tonight, and GPT says K-means after the deadline. **Call:** stretch goal only. It needs a personal baseline we can't collect in time.
- **Confusion check.** Gemini proposes a Vibro-triggered tap test on the watch, and GPT proposes carer-entered observations. **Call:** do both cheaply. A one-tap check on the dashboard (watch later) plus manual BP, confusion and urination entries that feed the full NEWS2.

## Ranked plan

| # | Item | Needs board? | Effort | Owner |
|---|---|---|---|---|
| 1 | LightGBM on 24 h trend features, exported through BYOM, matched comparison against the dense net and NEWS2 on identical windows | no | 1.5 h | main thread |
| 2 | Replay engine: pick a held-out sepsis patient and a non-sepsis patient; dashboard "Replay" mode at 1 h = 2 s with both scores and the alert time | no (build), yes (show) | 2 h | main thread (engine) + board thread (dashboard) |
| 3 | `.eim` (Linux aarch64) running in the App Lab container, with an offline test | yes | 1.5 h | main thread |
| 4 | IMU impulse `still` / `moving` (+ `shiver-like`): record 2 to 3 min per class on the LSM6DSOX, optionally pre-seeded from PAMAP2 chest IMU; Spectral Analysis + NN; EON Tuner numbers for the pitch | yes (recording) | 2.5 h | main thread (EI) + board thread (gating) |
| 5 | Check-in panel: one-tap confusion check, manual BP and urination entries, reading age on every vital, full NEWS2 when complete | no | 1 h | board thread |
| 6 | Thermo skin-minus-ambient gradient (peripheral cooling cue), if the Thermo is detected | yes | 30 min | board thread |
| 7 | Pitch: 30 s story, 60 s live sit-walk-sit, 60 s replay, 30 s results and limits; record a backup video | no | 2 h | team |
| Stretch | GMM anomaly on resting vitals; RR regression against a belt; MAX30101 perfusion index if one is on hand | | | |

## Honesty rules for the pitch

- Retrospective ICU data, not validated at home. Report sensitivity at a fixed false-alarm rate, not only AUC.
- The core temperature is a fixed-offset estimate from skin temperature.
- Rigors data is acted, so label it "shiver-like motion".
- The replay is labelled on screen as a recorded, accelerated ICU case.
- It's a decision-support prototype, not a diagnostic device.

## Datasets to use tonight

PhysioNet 2019 (in use), PAMAP2 chest IMU (open, CC BY 4.0) for activity pre-training. Gemini and GPT also list BIDMC, PPG-DaLiA, WESAD, CEBS, Auricle, VitalDB, SisFall and COUGHVID. I have not opened those links myself, so check each one before citing it.
