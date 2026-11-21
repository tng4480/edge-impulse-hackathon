"""Strict patient-level evaluation (after the Sol review).

- Operating points are chosen on VALIDATION patients only (train-split patients held out from
  fitting, used only for early stopping), then applied unchanged to the TEST patients.
- "Flagged before onset" counts alerts in the 24 h strictly before onset: hours onset-24 .. onset-1.
  Onset = first SepsisLabel hour + 6 (PhysioNet 2019 definition).
- NEWS2 uses the fixed rounding in news2.py (round half up before banding).
- False alerts = alert episodes (rising edges) per patient-day in non-sepsis patients.
Two operating points, both picked on validation:
  "same catch rate":    model catch rate ~= NEWS2 rule's catch rate (compare false alerts)
  "same alert burden":  model false alerts/day ~= NEWS2 rule's (compare catch rate)
Writes training/out/strict_eval.json.
"""
import glob
import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "board" / "sepsis-monitor" / "python"))
from features import VITALS, features  # noqa: E402
from model_runner import Trees  # noqa: E402
from news2 import news2  # noqa: E402

trees = Trees(ROOT / "training" / "out" / "model.json")


def h(pid, salt=""):
    return int(hashlib.md5((salt + pid).encode()).hexdigest(), 16) % 1000


def group(pid):
    if h(pid) < 200:
        return "test"
    return "val" if h(pid, "val") < 100 else "train"


def carried(rows):
    last = [None] * 4
    for r in rows:
        last = [v if v is not None else l for v, l in zip(r, last)]
    return last


def score_patient(rows):
    risk, n2 = np.full(len(rows), -1.0), np.zeros(len(rows), bool)
    for e in range(len(rows)):
        hist = rows[:e + 1]
        fv = features(hist)
        if fv is not None:
            risk[e] = trees.p_sepsis(fv)
            hr, o2, t, rr = carried(hist)
            s = news2(rr=rr, spo2=o2, temp=t, hr=hr)
            n2[e] = s["score"] >= 5 or s["any_red"]   # same 8 h start as the model
    return risk, n2


def collect(which):
    seps, heal = [], []
    for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv"))):
        pid = pathlib.Path(f).stem
        if group(pid) != which:
            continue
        df = pd.read_csv(f, sep="|", usecols=list(VITALS) + ["SepsisLabel"])
        rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
        lab = df["SepsisLabel"].to_numpy()
        risk, n2 = score_patient(rows)
        if lab.max() == 1:
            onset = int(np.argmax(lab == 1)) + 6
            if onset >= 9:  # need at least one scorable hour before onset
                seps.append((risk, n2, onset))
        else:
            heal.append((risk, n2))
    print(which, len(seps), "sepsis,", len(heal), "non-sepsis", flush=True)
    return seps, heal


def episodes(flags):
    f = np.asarray(flags, bool)
    return int(f[0]) + int((f[1:] & ~f[:-1]).sum()) if len(f) else 0


def metrics(seps, heal, thr=None):
    """thr=None -> NEWS2 rule; else model risk >= thr."""
    flag = (lambda r, n: n) if thr is None else (lambda r, n: r >= thr)
    caught = [flag(r, n)[max(0, o - 24):o].any() for r, n, o in seps]
    hours = sum(max(0, (r >= 0).sum()) for r, n in heal)
    eps = sum(episodes(flag(r, n)[r >= 0]) for r, n in heal)
    return {"flagged_before_onset": round(float(np.mean(caught)), 3),
            "false_alerts_per_patient_day": round(eps / (hours / 24), 2)}


def main():
    val_s, val_h = collect("val")
    tst_s, tst_h = collect("test")
    grid = np.round(np.arange(0.30, 0.86, 0.01), 2)
    n2_val = metrics(val_s, val_h)
    val_curve = {float(t): metrics(val_s, val_h, t) for t in grid}
    same_catch = min(grid, key=lambda t: abs(val_curve[float(t)]["flagged_before_onset"] - n2_val["flagged_before_onset"]))
    same_burden = min(grid, key=lambda t: abs(val_curve[float(t)]["false_alerts_per_patient_day"] - n2_val["false_alerts_per_patient_day"]))
    res = {
        "definition": "alerts in the 24 h strictly before onset (onset = first label + 6 h); thresholds chosen on validation patients",
        "validation": {"news2_rule": n2_val, "same_catch_threshold": float(same_catch), "same_burden_threshold": float(same_burden),
                       "n_sepsis": len(val_s), "n_nonsepsis": len(val_h)},
        "test": {"n_sepsis": len(tst_s), "n_nonsepsis": len(tst_h),
                 "news2_rule": metrics(tst_s, tst_h),
                 "model_same_catch": {"threshold": float(same_catch), **metrics(tst_s, tst_h, float(same_catch))},
                 "model_same_burden": {"threshold": float(same_burden), **metrics(tst_s, tst_h, float(same_burden))},
                 "model_val_15pct_window_threshold": {"threshold": 0.614, **metrics(tst_s, tst_h, 0.614)}},
    }
    print(json.dumps(res, indent=1))
    (ROOT / "training" / "out" / "strict_eval.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
