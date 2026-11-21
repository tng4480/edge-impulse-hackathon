"""Train the LightGBM sepsis model on 24 h trend features and compare it, on IDENTICAL windows,
with the Edge Impulse dense net and the 4-vital NEWS2 baseline.

- Features: board/sepsis-monitor/python/features.py (the board runs the same code).
- Split: same md5 patient hash as prep_windows.py (20 % test). Train patients are split again
  (10 %) into a validation set used only to choose the alert threshold.
- Matched test set: the exact 1,200 windows uploaded to Edge Impulse (data/ei/testing), so
  all three methods score the same patient-hours.
Outputs in training/out/: model.txt, model.json (tree dump), meta.json, comparison.json.
"""
import glob
import hashlib
import json
import os
import pathlib
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "board" / "sepsis-monitor" / "python"))
from features import FEATURE_NAMES, VITALS, features  # noqa: E402
from news2 import news2  # noqa: E402

OUT = ROOT / "training" / "out"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(42)


def h(pid, salt=""):
    return int(hashlib.md5((salt + pid).encode()).hexdigest(), 16) % 1000


def load(path):
    df = pd.read_csv(path, sep="|", usecols=list(VITALS) + ["SepsisLabel"])
    rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
    return rows, df["SepsisLabel"].to_numpy()


def candidate_ends(lab, n):
    if lab.max() == 1:
        fp = int(np.argmax(lab == 1))
        return [e for e in range(7, n) if lab[e] == 1], [e for e in range(7, n) if e <= fp - 12]
    return [], list(range(7, n))


def news2_last(hist):
    # Score the last hour with values carried forward, as the board would see them.
    last = [None] * 4
    for row in hist:
        last = [v if v is not None else l for v, l in zip(row, last)]
    hr, o2, t, rr = last
    return news2(rr=rr, spo2=o2, temp=t, hr=hr)


def main():
    files = sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv")))
    by_pid = {pathlib.Path(f).stem: f for f in files}
    matched = []
    for f in glob.glob(str(ROOT / "data" / "ei" / "testing" / "*.csv")):
        label, rest = pathlib.Path(f).stem.split(".", 1)
        pid, end = rest.rsplit("_", 1)
        matched.append((pid, int(end), label == "sepsis"))
    matched_pids = {m[0] for m in matched}

    X = {"train": [], "val": []}
    y = {"train": [], "val": []}
    cache = {}
    for i, (pid, f) in enumerate(by_pid.items()):
        if h(pid) < 200:  # test patient
            if pid in matched_pids:
                cache[pid] = load(f)
            continue
        rows, lab = load(f)
        if len(rows) < 8:
            continue
        pos, neg = candidate_ends(lab, len(rows))
        split = "val" if h(pid, "val") < 100 else "train"
        for e, yy in [(e, 1) for e in RNG.permutation(pos)[:3]] + [(e, 0) for e in RNG.permutation(neg)[:2]]:
            fv = features(rows[:int(e) + 1])
            if fv is not None:
                X[split].append(fv)
                y[split].append(yy)
        if i % 10000 == 0:
            print("scanned", i, flush=True)

    Xtr, ytr = np.array(X["train"]), np.array(y["train"])
    Xva, yva = np.array(X["val"]), np.array(y["val"])
    print("train", np.bincount(ytr), "val", np.bincount(yva))

    model = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=50,
                               subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                               class_weight="balanced", verbose=-1)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="auc",
              callbacks=[lgb.early_stopping(40, verbose=False)])
    pva = model.predict_proba(Xva)[:, 1]
    thr = float(np.quantile(pva[yva == 0], 0.85))  # 15 % alarm rate on validation healthy windows
    print(f"val AUC {roc_auc_score(yva, pva):.3f}, threshold @15% FA = {thr:.3f}, trees {model.best_iteration_}")

    # Matched test set
    Xt, yt, n2 = [], [], []
    for pid, end, is_sep in matched:
        rows, _ = cache[pid]
        hist = rows[:end + 1]
        Xt.append(features(hist))
        yt.append(is_sep)
        n2.append(news2_last(hist))
    Xt, yt = np.array(Xt), np.array(yt)
    pt = model.predict_proba(Xt)[:, 1]
    s = np.array([n["score"] for n in n2])
    red = np.array([n["any_red"] for n in n2])

    def at_fa(p, fa):
        t = np.quantile(p[~yt], 1 - fa)
        return float((p[yt] > t).mean())

    res = {
        "n_windows": int(len(yt)), "n_sepsis": int(yt.sum()),
        "lightgbm": {"auc": roc_auc_score(yt, pt), "pr_auc": average_precision_score(yt, pt),
                     "sens_at_5pct_fa": at_fa(pt, 0.05), "sens_at_15pct_fa": at_fa(pt, 0.15),
                     "at_val_threshold": {"sens": float((pt[yt] >= thr).mean()),
                                          "false_alarm": float((pt[~yt] >= thr).mean())}},
        "news2": {"auc": roc_auc_score(yt, s), "pr_auc": average_precision_score(yt, s),
                  "score5_or_red": {"sens": float(((s >= 5) | red)[yt].mean()),
                                    "false_alarm": float(((s >= 5) | red)[~yt].mean())}},
    }
    probs = ROOT / "training" / "test_probs_named.json"
    if probs.exists():  # Edge Impulse dense net, by filename
        d = json.loads(probs.read_text())
        pd_ = np.array([d[f"{'sepsis' if ys else 'healthy'}.{pid}_{end}"] for (pid, end, ys) in matched])
        res["dense_net_ei"] = {"auc": roc_auc_score(yt, pd_), "pr_auc": average_precision_score(yt, pd_),
                               "sens_at_5pct_fa": at_fa(pd_, 0.05), "sens_at_15pct_fa": at_fa(pd_, 0.15)}
    print(json.dumps(res, indent=1))

    model.booster_.save_model(str(OUT / "model.txt"))
    (OUT / "model.json").write_text(json.dumps(model.booster_.dump_model()))
    (OUT / "meta.json").write_text(json.dumps({
        "features": FEATURE_NAMES, "threshold": thr, "threshold_rule": "15% alarm rate on validation healthy windows",
        "trees": int(model.best_iteration_ or model.n_estimators)}, indent=1))
    (OUT / "comparison.json").write_text(json.dumps(res, indent=1))
    np.save(OUT / "val_features.npy", Xva.astype(np.float32))


if __name__ == "__main__":
    main()
