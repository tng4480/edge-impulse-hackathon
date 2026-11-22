"""LightGBM v2: train on the early-warning target we actually evaluate (Neon v2 finding).

v1 (train_gbm.py) used every SepsisLabel==1 hour as positive (from onset-6 through and after
onset) and labelled sepsis patients' hours up to onset-18 as negative, so it learned
"sepsis is present" and called the early-warning hours [onset-24, onset-18] healthy.

v2 labels, onset = first SepsisLabel hour + 6:
  positive: windows ending in [onset-24, onset-1]       (the window strict_eval scores)
  negative: any window in non-sepsis patients, and sepsis patients' windows ending <= onset-48
  excluded: everything else (onset-47..onset-25, and onset onwards)
Same features, same patient split and validation patients as v1. Output: training/out/v2/.
Then: MODEL_JSON=training/out/v2/model.json OUT_TAG=v2 python training/strict_eval.py
"""
import glob
import hashlib
import json
import pathlib
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "board" / "sepsis-monitor" / "python"))
from features import FEATURE_NAMES, VITALS, features  # noqa: E402

import os
MASK_TEMP = os.environ.get("MASK_TEMP") == "1"   # v3: the device has no core temperature, so train without it
OUT = ROOT / "training" / "out" / os.environ.get("OUT_DIR", "v2")
RNG = np.random.default_rng(42)


def h(pid, salt=""):
    return int(hashlib.md5((salt + pid).encode()).hexdigest(), 16) % 1000


def ends(lab, n):
    if lab.max() == 1:
        onset = int(np.argmax(lab == 1)) + 6
        return ([e for e in range(7, n) if onset - 24 <= e <= onset - 1],
                [e for e in range(7, n) if e <= onset - 48])
    return [], list(range(7, n))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    X = {"train": [], "val": []}
    y = {"train": [], "val": []}
    files = sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv")))
    for i, f in enumerate(files):
        pid = pathlib.Path(f).stem
        if h(pid) < 200:
            continue  # test patient
        df = pd.read_csv(f, sep="|", usecols=list(VITALS) + ["SepsisLabel"])
        rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
        if MASK_TEMP:
            rows = [[r[0], r[1], None, r[3]] for r in rows]   # Temp is index 2; features() fills the default
        lab = df["SepsisLabel"].to_numpy()
        if len(rows) < 8:
            continue
        pos, neg = ends(lab, len(rows))
        split = "val" if h(pid, "val") < 100 else "train"
        for e, yy in [(e, 1) for e in RNG.permutation(pos)[:8]] + [(e, 0) for e in RNG.permutation(neg)[:3]]:
            fv = features(rows[:int(e) + 1])
            if fv is not None:
                X[split].append(fv)
                y[split].append(yy)
        if i % 10000 == 0:
            print("scanned", i, flush=True)
    Xtr, ytr = np.array(X["train"]), np.array(y["train"])
    Xva, yva = np.array(X["val"]), np.array(y["val"])
    print("train", np.bincount(ytr), "val", np.bincount(yva), flush=True)
    model = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=15, min_child_samples=50,
                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                               class_weight="balanced", verbose=-1)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="auc",
              callbacks=[lgb.early_stopping(40, verbose=False)])
    pva = model.predict_proba(Xva)[:, 1]
    print(f"val window AUC {roc_auc_score(yva, pva):.3f}, trees {model.best_iteration_}", flush=True)
    model.booster_.save_model(str(OUT / "model.txt"))
    (OUT / "model.json").write_text(json.dumps(model.booster_.dump_model()))
    (OUT / "meta.json").write_text(json.dumps({"features": FEATURE_NAMES, "trees": int(model.best_iteration_ or 0),
                                               "target": "windows ending onset-24..onset-1 vs non-sepsis / <= onset-48"}, indent=1))


if __name__ == "__main__":
    main()
