# Edge Impulse Technical Story (Judge Verification Page)

We used Edge Impulse across **two separate Studio projects** — one for tabular physiological trends (**Bring Your Own Model**) and one for spoken-digit audio (**native Audio MFCC + Keras KWS**) — because impulses inside a single Edge Impulse project share one dataset ([Edge Impulse BYOM](https://docs.edgeimpulse.com/studio/projects/dashboard/byom), [Audio MFCC](https://docs.edgeimpulse.com/studio/projects/processing-blocks/blocks/audio-mfcc)). Every claim below links to the exact repository file a judge can inspect.

---

## 1. Why BYOM for Sepsis Risk (Overcoming the Free-Plan Classical-ML Limit)
- **Baseline comparison on identical windows:** We first built a native Edge Impulse Dense NN on 8 h raw vitals, which reached **0.698 ROC AUC** (15% sensitivity at 5% false alarms) on 1,200 held-out PhysioNet 2019 test windows. A 176-tree LightGBM on 32 causal 24 h trend features (last, mean, min, max, std, 1 h delta, 6 h delta, slope across HR, SpO₂, Temp, Resp) reached **0.745 ROC AUC** (24% at 5% FA) vs **0.642** for 4-vital NEWS2 (`training/train_gbm.py`, `training/out/comparison.json`, `docs/results.md`).
- **Hummingbird GEMM → ONNX bridge:** Edge Impulse's free tier does not build classical-ML (`lgbm`) blocks natively. We compiled the trained LightGBM booster into standard tensor operations using **Hummingbird (`tree_implementation="gemm"`)** wrapped with a sigmoid two-class `[P(healthy), P(sepsis)]` head and exported to ONNX opset 13 (`training/to_onnx.py` → `training/out/model_gemm.onnx`).
- **Numerical parity:** `training/to_onnx.py` checks maximum absolute probability difference between ONNX Runtime and LightGBM across 1,000 validation rows; Edge Impulse's output matches LightGBM to **4 decimal places** (`docs/results.md`).
- **Automated Studio upload & build:** `training/byom_upload.py` uploads `model_gemm.onnx` to project `1169195` (`training/ei.py`) as a dedicated impulse (**impulse #4**, leaving impulses #1 and #2 untouched), configures 32 raw features → `["healthy", "sepsis"]`, builds `runner-linux-aarch64` (`float32`), and downloads the `.eim` binary (`training/out/sepsis-lgbm-aarch64.eim`, deployed to `board/sepsis-monitor/python/model/sepsis.eim`).

## 2. Offline Linux aarch64 `.eim` Execution on Arduino UNO Q
- **Shared feature code:** Both training/evaluation and the UNO Q app import the exact same pure-Python feature extractor (`board/sepsis-monitor/python/features.py`), eliminating train/serve feature skew.
- **On-board runner protocol:** `board/sepsis-monitor/python/model_runner.py` (`EimRunner`) launches `model/sepsis.eim` over a local Unix domain socket (`runner.sock`), sends JSON classification requests, and reads NUL-terminated replies completely offline ([Edge Impulse Linux SDK](https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/python)). `board/sepsis-monitor/python/main.py` serializes calls via `MODEL_LOCK` across live hourly scoring, accelerated ICU replay (`replay.py`), and the interactive stress lab (`stress.py`).
- **Deterministic fallback:** If `sepsis.eim` is absent or fails to start, `model_runner.py` (`Trees`) evaluates the exact same 176 trees from `board/sepsis-monitor/python/model/model.json` and surfaces the active engine (`eim` vs `trees`) on the dashboard liveness chip (`dashboard.html`) and inside exported FHIR `Provenance` records (`fhir.py`).

## 3. Second Edge Impulse Project: Spoken-Digit Attention Check (And Why We Killed Slurred Speech)
- **What we tested and rejected:** Before touching Edge Impulse audio, we ran a strict **leave-one-speaker-out** feasibility test on TORGO (16,544 clips, 15 speakers; `training/speech_baseline.py`, `training/out/speech_baseline.json`, `docs/research/speech.md`). Clip AUC was only **0.635**, fell when holding microphone fixed (**0.669** head mic vs **0.592** array mic — recording bias consistent with [arXiv:2509.19946](https://arxiv.org/abs/2509.19946)), scored healthy speaker `MC04` (0.64) above 3 of 8 dysarthric speakers, and missed dysarthric `F03` on **93%** of clips. We refused to ship it.
- **Native Edge Impulse digit KWS:** We pivoted to a bedside **digits-backwards attention check** feeding NEWS2 "C" (new confusion), with a tap/carer fallback. `training/speech_kws.py` prepares 12 classes (`zero`..`nine`, `unknown`, synthetic `noise`) from the official **speaker-disjoint** splits of Google Speech Commands v2 (CC BY 4.0, [arXiv:1804.03209](https://arxiv.org/abs/1804.03209)) — 600 train and 120 test clips per class (`training/out/speech/prep.json`).
- **Impulse & `.eim` build:** Configured via Edge Impulse REST API (`training/speech_kws.py`, `training/out/speech/impulse.json`): 16 kHz Audio (1,000 ms window, 500 ms hop) → **Audio (MFCC)** DSP block → **Keras Classification** → `runner-linux-aarch64` (`int8`) binary (`training/out/speech/digits.eim`, 13.5 MB). Validation accuracy: **89.6% (`int8`)** vs **89.4% (`float32`)** (`training/out/speech_train.log`).
- **On-board sequence decoder:** `board/sepsis-monitor/python/attention.py` slides a 1 s window at 250 ms hop over spoken answers, merges consecutive confident runs (`p ≥ 0.6`, ≥ 2 windows), and compares decoded digits against the reversed prompt.

## 4. Strict Held-Out Evaluation & Validation-Chosen Threshold
- **Zero speaker/patient leakage:**
  - *Sepsis:* Deterministic MD5 patient hash split (`training/strict_eval.py`) separates train, validation (**184 sepsis / 2,926 non-sepsis**), and held-out test (**476 sepsis / 7,422 non-sepsis**). `ICULOS` (hours since ICU admission) is excluded despite lifting AUC to 0.84 because it is an ICU dataset artefact (`docs/results.md`).
  - *Speech:* Official speaker-disjoint Speech Commands v2 test split + synthetic multi-digit held-out-speaker sequence generator (`training/speech_seq_eval.py`) and on-board `.eim` test harness (`board/sepsis-monitor/python/attention_selftest.py`). *(Note: end-to-end 4-digit sequence accuracy from `attention_selftest.py` is not yet logged in the repo — unverified until run on hardware.)*
- **Validation-chosen threshold (`0.55`):** Earlier test-set threshold picking (`0.58`) was scrapped after internal review. In `training/strict_eval.py`, the deployed cutoff **`0.55`** (`board/sepsis-monitor/python/model/meta.json`) was chosen **exclusively on validation patients** to match 4-vital NEWS2's catch rate, then frozen and evaluated once on the 7,898 held-out test patients (`training/out/strict_eval.json`) and across 7 failure-mode stressors (`training/stress_eval.py`, `training/out/stress_eval.json`, `docs/stress_results.md`).

---

## Judge Verification Map

| Claim | Exact Repo File Path | What to Verify |
|---|---|---|
| Shared 32 trend features (train = board) | `board/sepsis-monitor/python/features.py` | 24 h window, `MIN_HOURS = 8`, causal carry-forward |
| LightGBM vs EI Dense NN vs NEWS2 (1,200 windows) | `training/train_gbm.py`, `training/out/comparison.json` | ROC AUC `0.745` vs `0.698` vs `0.642` |
| Hummingbird GEMM → ONNX & parity check | `training/to_onnx.py` | GEMM tree conversion + 1,000-row diff check vs LightGBM |
| Edge Impulse BYOM upload & aarch64 `.eim` build | `training/byom_upload.py`, `training/ei.py` | Project `1169195`, impulse #4, `runner-linux-aarch64` |
| On-board `.eim` Unix-socket runner + tree fallback | `board/sepsis-monitor/python/model_runner.py` | `EimRunner` protocol, `Trees` fallback, `meta.json` threshold `0.55` |
| Validation-chosen threshold & strict patient eval | `training/strict_eval.py`, `training/out/strict_eval.json` | Val split (184/2,926) picks `0.55`; test split (476/7,422) never tunes cutoffs |
| No-core-temperature ablation (v3) | `training/train_gbm_v2.py`, `training/out/strict_eval_v3.json` | `MASK_TEMP=1` honest 3-vital trade-off (`docs/results.md`) |
| 7-scenario stress evaluation | `training/stress_eval.py`, `training/out/stress_eval.json` | SpO₂ +2/+4, missing/sparse SpO₂, beta-blocker, walk, no temp |
| Rejected TORGO slurred-speech baseline | `training/speech_baseline.py`, `training/out/speech_baseline.json` | Leave-one-speaker-out clip AUC `0.635`, mic bias, `F03`/`MC04` |
| Digit KWS Edge Impulse project & `.eim` | `training/speech_kws.py`, `training/out/speech_train.log` | Speaker-disjoint prep, MFCC+Keras impulse, `89.6%` `int8` val acc, `digits.eim` |
| Held-out-speaker sequence eval & decoder | `training/speech_seq_eval.py`, `board/sepsis-monitor/python/attention.py`, `board/sepsis-monitor/python/attention_selftest.py` | Sliding-window decoder + held-out speaker test harness |
