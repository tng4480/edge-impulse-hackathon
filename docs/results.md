# Model results (for the pitch)

All numbers are on **held-out PhysioNet 2019 patients** (a patient-level split by md5 hash; no test patient was used in training or for choosing features). These are retrospective ICU data, not validated at home.

## The model

- **What it is:** LightGBM, 176 trees, on 32 trend features. For each of HR, SpO2, temperature and respiratory rate over the last 24 hourly readings it uses last, mean, min, max, standard deviation, 1 h change, 6 h change and slope. The code is `board/sepsis-monitor/python/features.py`, shared by training and the board.
- **Deployment:** brought into Edge Impulse with **Bring Your Own Model** as impulse #4. The free plan can't build classical-ML models, so the trees were compiled to standard tensor ops (Hummingbird GEMM to ONNX). Edge Impulse's output matches LightGBM to 4 decimal places (`training/byom_upload.py`, `training/to_onnx.py`).
- **On the board:** a Linux aarch64 `.eim`, run offline through the Edge Impulse runner protocol. A pure-Python evaluator of the same trees is the fallback, and it matches exactly (`model_runner.py`).

## Window-level comparison (identical 1,200 test windows, 600 sepsis)

| Method | ROC AUC | Sepsis caught at 5 % false alarms | at 15 % |
|---|---|---|---|
| NEWS2, 4 vitals | 0.642 | 17 % (score 5+) | 34 % (5+ or any 3) |
| Dense NN in Edge Impulse, 8 h raw | 0.698 | 15 % | 38 % |
| **LightGBM, 24 h trends** | **0.745** | **24 %** | **43 %** |

## Patient-level, hour by hour, as the device would run (476 sepsis and 7,422 non-sepsis test patients)

Strict protocol (`training/strict_eval.py`, output `training/out/strict_eval.json`), revised after the Sol review:

- **Cutoffs were chosen on validation patients only.** These 184 sepsis and 2,926 non-sepsis patients come from the training split but were held out of fitting. The test set was never used to pick a number.
- Onset is the first SepsisLabel hour plus 6, the challenge's definition. "Flagged" means an alert in the 24 h **strictly before** onset, hours onset−24 to onset−1.
- Both methods start scoring at the same hour, once 8 h of history exist. NEWS2 rounds readings before banding, as a chart would.
- False alerts are alert episodes (each run of consecutive alert hours counts once) per patient-day in non-sepsis patients.

| Method (test patients) | Flagged before onset | False alerts per patient-day |
|---|---|---|
| NEWS2 rule, 4 vitals (score 5+ or any 3) | 76 % | 1.61 |
| **Model score ≥ 0.55** (matches NEWS2's catch rate on validation) | **78 %** | **0.91** |
| Model score ≥ 0.30 (still fewer false alerts than NEWS2 on validation) | 97 % | 1.46 |
| Model score ≥ 0.614 (validation, 15 % window false-alarm rate) | 69 % | 0.71 |

The device uses **0.55**. 0.30 was the bottom of the searched range, so the "same burden" point is a lower bound: the cutoff where false alerts exactly match NEWS2 is lower still.

**Pitch line:** at the same catch rate as a 4-vital NEWS2 rule, the model raises about 43 % fewer false alerts (0.91 vs 1.61 per patient-day). Lower the cutoff and it catches nearly all sepsis patients in the day before onset while still alarming less than NEWS2. This is a model score, not a calibrated probability of sepsis.

The earlier table (cutoff 0.58, chosen on the test set, with a window that included the onset hour) is superseded.

## Replay cases (`board/sepsis-monitor/python/replay_cases.json`)

- **Sepsis, p112060:** shows hours 83 to 115, about 50 s at 1.5 s per hour. At the device cutoff 0.55 the model alerts at hour 89, 24 h before onset (hour 113), and the NEWS2 rule does not alert in that window. It was chosen as the median-lead case among qualifying patients, so it is **illustrative, not typical**.
- **Non-sepsis, p000147:** shows hours 8 to 42, and neither method alerts.

## Caveats to say out loud

- ICU data: vitals are charted by nurses, the patients are sicker, and treatment changes the trajectories. Home performance needs prospective data.
- The NEWS2 comparison uses 4 of its 7 parameters (no BP, consciousness or supplemental oxygen).
- "Hours since ICU admission" would raise the AUC to 0.84 but is a dataset artefact, so it is excluded.
- The device estimates core temperature from wrist skin temperature with a fixed offset.
