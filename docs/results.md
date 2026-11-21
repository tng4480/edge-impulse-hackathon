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

## Patient-level, hour by hour, as the device would run (492 sepsis and 7,422 non-sepsis test patients)

Onset is the first SepsisLabel hour plus 6, the challenge's definition. "Flagged" means an alert in the 24 h before onset. False alerts are alert episodes per patient-day in non-sepsis patients.

| Method | Flagged before onset | False alerts per patient-day |
|---|---|---|
| NEWS2 rule (score 5+ or any 3) | 75 % | 1.60 |
| **Model at the device threshold 0.58** | **74 %** | **0.82** |
| Model at 0.50 | 83 % | 1.07 |
| Model at 0.40 | 91 % | 1.34 |

**Pitch line:** the model matches NEWS2's catch rate with about half the false alerts. Or, accepting fewer false alerts than NEWS2, it flags 91 % of sepsis patients against NEWS2's 75 %.

## Replay cases (`board/sepsis-monitor/python/replay_cases.json`)

- **Sepsis, p112060:** shows hours 83 to 115, about 50 s at 1.5 s per hour. The model alerts at hour 89, 24 h before onset (hour 113), and the NEWS2 rule does not alert in that window. It was chosen as the median-lead case among qualifying patients, so it is **illustrative, not typical**.
- **Non-sepsis, p000147:** shows hours 8 to 42, and neither method alerts.

## Caveats to say out loud

- ICU data: vitals are charted by nurses, the patients are sicker, and treatment changes the trajectories. Home performance needs prospective data.
- The NEWS2 comparison uses 4 of its 7 parameters (no BP, consciousness or supplemental oxygen).
- "Hours since ICU admission" would raise the AUC to 0.84 but is a dataset artefact, so it is excluded.
- The device estimates core temperature from wrist skin temperature with a fixed offset.
