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

| Method (test patients) | Flagged before onset | Separate false alerts per patient-day | Share of non-sepsis hours in alert | Median first alert before onset |
|---|---|---|---|---|
| NEWS2 rule, 4 vitals (score 5+ or any 3) | 76 % | 1.61 | 16 % | 17 h |
| **Model ≥ 0.55** (cutoff matching NEWS2's catch rate on validation; on the device) | **78 %** | **0.91** | 22 % | 20 h |
| Model ≥ 0.61 (cutoff matching NEWS2's time in alert on validation) | 70 % | 0.72 | 15 % | 18 h |
| Model ≥ 0.30 (cutoff matching NEWS2's separate alerts on validation) | 97 % | 1.46 | 64 % | 24 h |

**What this shows, honestly:**

- **At the same catch rate,** the model raises about 43 % fewer separate false alerts and warns about 3 h earlier (median). But each alert lasts longer: non-sepsis patients are in alert 22 % of hours against 16 %.
- **At the same total alarm time,** NEWS2 catches more: 76 % against 70 %. The model does **not** beat a 4-vital NEWS2 on catches per alarm-hour.
- **The 0.30 row is not usable.** The alarm is on 64 % of the time, so a high catch rate there means nothing.
- **The model's real advantage is the shape of its alarms:** fewer, steadier and slightly earlier, because it follows 24 h trends while NEWS2 flips with each reading. For a home wearer, one steady alert to act on may matter more than raw alarm time, but this data doesn't prove that.
- This is a model score, not a calibrated probability of sepsis. All four rows come from `training/out/strict_eval.json`, and the full cutoff curves are in `strict_curves.json`.

**Pitch line:** "Matching NEWS2's catch rate, our model raises 43 % fewer separate alarms and warns about three hours earlier. It does not beat NEWS2 on total alarm time, which is why the device also runs NEWS2 alongside it."

The earlier table (cutoff 0.58, chosen on the test set, with a window that included the onset hour) is superseded.

## What the device can actually measure: no core temperature

The table above uses recorded ICU temperature, which the watch can't provide (it reads wrist skin, not core). `training/train_gbm_v2.py` and `training/strict_eval.py` with `MASK_TEMP=1` train and score everything on HR, SpO2 and respiratory rate only (model v3, NEWS2 scored on the same three vitals). Cutoffs again chosen on validation patients; results in `training/out/strict_eval_v3.json`.

| Method (test patients, no temperature) | Flagged before onset | Separate false alerts per patient-day | Share of non-sepsis hours in alert | Median first alert before onset |
|---|---|---|---|---|
| NEWS2 rule, 3 vitals | 73 % | 1.58 | 15 % | 17 h |
| Model v3 ≥ 0.52 (matches NEWS2's catch rate on validation) | 78 % | 1.06 | 32 % | 23 h |
| Model v3 ≥ 0.61 (matches NEWS2's time in alert on validation) | 60 % | 0.68 | 16 % | 19 h |

- The model still gives a longer warning (23 h against 17 h) and fewer separate alerts at a similar catch rate, but it spends **twice as long in alert** (32 % against 15 %).
- At the same alarm time the model catches **fewer** (60 % against 73 %). On the signals the device really has, the model does not beat NEWS2 on catches per alarm-hour.
- The stress lab says the same thing for the v1 model: with temperature removed its catch rate falls from 78 % to 55 % (`docs/stress_results.md`).
- The device currently runs the v1 model, which was trained with temperature. With no temperature the board fills in a default of 36.9 °C, so live performance is closer to the stress-lab row than to the first table. v3 is trained for exactly that situation but is not deployed.

### Can an alert policy close the gap? (`training/policy_eval.py`)

The v3 score is sticky, so I searched about 580 rules on validation patients only: turn on after k consecutive hours at or above a cutoff, turn off when the score drops below a lower cutoff, or after a maximum number of hours. Each winner is then reported once on the test patients.

| Test patients, no temperature | Flagged before onset | Separate false alerts per patient-day | Share of non-sepsis hours in alert | Median first alert before onset |
|---|---|---|---|---|
| NEWS2 rule, 3 vitals | 73 % | 1.58 | 15 % | 17 h |
| Model, bare cutoff, equal alarm time | 50 % | 0.53 | 11 % | 18 h |
| **Model, best rule at equal alarm time** (3 h above 0.55, clear after 6 h) | **61 %** | 0.79 | 15 % | 20 h |
| **Model, best rule at NEWS2's separate-alert count** (3 h above 0.49, clear after 6 h) | **73 %** | 1.17 | 23 % | 22 h |

- A policy helps: at equal alarm time it lifts the model from 50 % to 61 %, and at a similar catch rate it cuts alarm time from 32 % (bare cutoff, previous table) to 23 %.
- It does **not** change the verdict. At equal alarm time NEWS2 still catches more (73 % against 61 %). The remaining gap comes from the signal, not the alert rule.
- The second rule is the honest best case for the pitch: the same catch rate as NEWS2 with about a quarter fewer separate alerts and a warning about 5 h earlier, but about 50 % more alarm time.
- This is a search over about 580 rules, so the validation winner is optimistic; the test numbers above are the ones to quote.

## Replay cases (`board/sepsis-monitor/python/replay_cases.json`)

- **Sepsis, p112060:** shows hours 83 to 115, about 50 s at 1.5 s per hour. At the device cutoff 0.55 the model alerts at hour 89, 24 h before onset (hour 113), and the NEWS2 rule does not alert in that window. It was chosen as the median-lead case among qualifying patients, so it is **illustrative, not typical**.
- **Non-sepsis, p000147:** shows hours 8 to 42, and neither method alerts.

## Caveats to say out loud

- ICU data: vitals are charted by nurses, the patients are sicker, and treatment changes the trajectories. Home performance needs prospective data.
- The NEWS2 comparison uses 4 of its 7 parameters (no BP, consciousness or supplemental oxygen).
- "Hours since ICU admission" would raise the AUC to 0.84 but is a dataset artefact, so it is excluded.
- The device estimates core temperature from wrist skin temperature with a fixed offset.
