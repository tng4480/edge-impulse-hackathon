"""Quick experiment: does LightGBM on longer windows + trend features beat the 8 h dense net?

Same patient-level split as prep_windows.py (md5 hash, 20 % test). Same labels:
sepsis = SepsisLabel 1 at the window's last hour; healthy = non-sepsis patients, or
sepsis patients 12+ h before their first positive label.
Feature sets: 'wearable' (HR, O2Sat, Temp, Resp only) and '+age' (adds Age).
"""
import glob, hashlib, sys
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score

V = ["HR", "O2Sat", "Temp", "Resp"]
RNG = np.random.default_rng(0)

def is_test(pid):
    return int(hashlib.md5(pid.encode()).hexdigest(), 16) % 1000 < 200

def feats(df, end, W):
    blk = df[V].iloc[max(0, end - W + 1):end + 1]
    f = {}
    t = np.arange(len(blk))
    for v in V:
        x = blk[v].to_numpy(float)
        f[f"{v}_last"] = x[-1]
        f[f"{v}_mean"] = np.nanmean(x); f[f"{v}_min"] = np.nanmin(x); f[f"{v}_max"] = np.nanmax(x)
        f[f"{v}_std"] = np.nanstd(x)
        f[f"{v}_d1"] = x[-1] - x[-2] if len(x) > 1 else 0
        f[f"{v}_d6"] = x[-1] - x[max(0, len(x) - 7)]
        ok = ~np.isnan(x)
        f[f"{v}_slope"] = np.polyfit(t[ok], x[ok], 1)[0] if ok.sum() > 2 else 0
    f["shock_index"] = f["HR_last"] / 120.0  # placeholder scale; no BP on a wearable
    f["hours"] = end + 1
    f["Age"] = df["Age"].iloc[0]
    return f

rows = {"train": [], "test": []}
files = sorted(glob.glob("data/raw/[AB]/p*.psv"))
W = int(sys.argv[1]) if len(sys.argv) > 1 else 24
for i, fpath in enumerate(files):
    pid = fpath.split("\\")[-1].split("/")[-1][:-4]
    df = pd.read_csv(fpath, sep="|", usecols=V + ["Age", "SepsisLabel"])
    df[V] = df[V].ffill()
    if df[V].isna().all().any():
        continue
    df[V] = df[V].bfill()
    lab = df["SepsisLabel"].to_numpy()
    n = len(df)
    if n < 8: continue
    if lab.max() == 1:
        fp = int(np.argmax(lab == 1))
        pos = [e for e in range(7, n) if lab[e] == 1]
        neg = [e for e in range(7, n) if e <= fp - 12]
    else:
        pos, neg = [], list(range(7, n))
    pos = list(RNG.permutation(pos)[:3]); neg = list(RNG.permutation(neg)[:2])
    split = "test" if is_test(pid) else "train"
    for e, y in [(e, 1) for e in pos] + [(e, 0) for e in neg]:
        f = feats(df, int(e), W); f["y"] = y; rows[split].append(f)
    if i % 10000 == 0: print("scanned", i, flush=True)

tr, te = pd.DataFrame(rows["train"]), pd.DataFrame(rows["test"])
print("train", tr.y.value_counts().to_dict(), "test", te.y.value_counts().to_dict())
for name, drop in (("wearable", ["Age", "hours"]), ("+age", ["hours"]), ("+age+hours-in-ICU", [])):
    cols = [c for c in tr.columns if c not in ["y"] + drop]
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, subsample=0.8,
                           colsample_bytree=0.8, class_weight="balanced", verbose=-1)
    m.fit(tr[cols], tr.y)
    p = m.predict_proba(te[cols])[:, 1]
    yv = te.y.to_numpy().astype(bool)
    thr = np.quantile(p[~yv], 0.85)
    print(f"W={W}h {name:20s} AUC {roc_auc_score(yv, p):.3f}  sens@15%FA {(p[yv] > thr).mean():.2f}")
