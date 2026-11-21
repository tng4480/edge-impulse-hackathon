"""Build Edge Impulse time-series windows from PhysioNet Challenge 2019.

Each window is WINDOW consecutive hourly rows of [HR, O2Sat, Temp, Resp].
Label "sepsis"  : the window's last hour has SepsisLabel == 1
                  (the challenge sets this from 6 h before clinical onset).
Label "healthy" : non-sepsis patients at any hour, plus sepsis patients'
                  windows ending 12+ h before the first positive label.

Patients are split into train/test BEFORE windowing so no patient appears in
both sets.

Time-lapse note: real data is 1 sample per HOUR. Edge Impulse CSVs get
1 sample per SECOND (TIMELAPSE_MS = 1000), i.e. 1 hour of patient time is
played as 1 s. The same factor applies to the demo replay on the board.
"""
import argparse
import hashlib
import pathlib

import numpy as np
import pandas as pd

VITALS = ["HR", "O2Sat", "Temp", "Resp"]
WINDOW = 8
TIMELAPSE_MS = 1000
RNG = np.random.default_rng(42)


def load_patient(path):
    df = pd.read_csv(path, sep="|", usecols=VITALS + ["SepsisLabel"])
    df[VITALS] = df[VITALS].ffill()
    return df


def is_test(pid, test_frac):
    h = int(hashlib.md5(pid.encode()).hexdigest(), 16) % 1000
    return h < test_frac * 1000


def windows_for(df, max_pos, max_neg):
    """Return (positive_end_indices, negative_end_indices) for one patient."""
    n = len(df)
    labels = df["SepsisLabel"].to_numpy()
    ends = np.arange(WINDOW - 1, n)
    # skip windows that still contain leading NaNs after ffill
    ok = [e for e in ends if not df[VITALS].iloc[e - WINDOW + 1:e + 1].isna().any().any()]
    ok = np.array(ok, dtype=int)
    if len(ok) == 0:
        return [], []
    if labels.max() == 1:
        first_pos = int(np.argmax(labels == 1))
        pos = [e for e in ok if labels[e] == 1]
        neg = [e for e in ok if e <= first_pos - 12]
    else:
        pos, neg = [], list(ok)
    pos = list(RNG.permutation(pos)[:max_pos]) if pos else []
    neg = list(RNG.permutation(neg)[:max_neg]) if neg else []
    return pos, neg


def write_window(df, end, label, pid, out_dir):
    block = df[VITALS].iloc[end - WINDOW + 1:end + 1].reset_index(drop=True)
    block.insert(0, "timestamp", np.arange(WINDOW) * TIMELAPSE_MS)
    block.to_csv(out_dir / f"{label}.{pid}_{end}.csv", index=False, float_format="%.2f")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/ei")
    ap.add_argument("--per-class-train", type=int, default=2500)
    ap.add_argument("--per-class-test", type=int, default=600)
    ap.add_argument("--test-frac", type=float, default=0.2)
    args = ap.parse_args()

    raw, out = pathlib.Path(args.raw), pathlib.Path(args.out)
    files = sorted(raw.glob("[AB]/p*.psv"))
    print(f"{len(files)} patient files")

    dirs = {}
    for split in ("training", "testing"):
        dirs[split] = out / split
        dirs[split].mkdir(parents=True, exist_ok=True)

    # Pass 1: choose candidate windows per patient, keep splits by patient hash.
    cand = {"training": {"sepsis": [], "healthy": []}, "testing": {"sepsis": [], "healthy": []}}
    for i, f in enumerate(files):
        pid = f.stem
        split = "testing" if is_test(pid, args.test_frac) else "training"
        df = load_patient(f)
        pos, neg = windows_for(df, max_pos=3, max_neg=2)
        for e in pos:
            cand[split]["sepsis"].append((f, int(e)))
        for e in neg:
            cand[split]["healthy"].append((f, int(e)))
        if i % 5000 == 0:
            print(f"  scanned {i}")

    quota = {"training": args.per_class_train, "testing": args.per_class_test}
    for split in cand:
        for label in ("sepsis", "healthy"):
            pool = cand[split][label]
            pick = RNG.permutation(len(pool))[:quota[split]]
            print(f"{split:8s} {label:8s} pool={len(pool):6d} using={len(pick)}")
            cache = {}
            for k in pick:
                f, e = pool[k]
                if f not in cache:
                    cache = {f: load_patient(f)}
                write_window(cache[f], e, label, f.stem, dirs[split])


if __name__ == "__main__":
    main()
