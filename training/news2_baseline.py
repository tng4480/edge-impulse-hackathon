"""NEWS2 baseline on the held-out test windows (patients never seen in training).

Scores each window's last hour with the same partial NEWS2 the board uses and reports
sensitivity / specificity at several alert thresholds, plus ROC AUC using the score itself.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board", "sepsis-monitor", "python"))
from news2 import news2  # noqa: E402

rows = []
for f in glob.glob("data/ei/testing/*.csv"):
    label = os.path.basename(f).split(".")[0]
    last = pd.read_csv(f).iloc[-1]
    n = news2(rr=last["Resp"], spo2=last["O2Sat"], temp=last["Temp"], hr=last["HR"])
    rows.append((label == "sepsis", n["score"], n["any_red"]))
y = np.array([r[0] for r in rows])
s = np.array([r[1] for r in rows])
red = np.array([r[2] for r in rows])
print(f"{len(y)} test windows, {y.sum()} sepsis")
print(f"ROC AUC of the NEWS2 score: {roc_auc_score(y, s):.3f}")
for thr in (3, 4, 5, 6, 7):
    pred = s >= thr
    print(f"score >= {thr}: sensitivity {pred[y].mean():.2f}, specificity {(~pred[~y]).mean():.2f}, "
          f"alarm rate on healthy {pred[~y].mean():.2f}")
pred = (s >= 5) | red
print(f"score >= 5 or any single 3: sensitivity {pred[y].mean():.2f}, specificity {(~pred[~y]).mean():.2f}")
