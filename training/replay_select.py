"""Hour-by-hour evaluation on ALL held-out test patients, as the device would run, plus replay cases.

For every test patient (same md5 split as training) the model and the 4-vital NEWS2 rule
(score >= 5 or any single 3) are evaluated at every hour from hour 8 on, using only the past.
- Sepsis onset = first SepsisLabel hour + 6 (the challenge's definition of clinical onset).
- "Flagged before onset": first alert falls within the 24 h before onset.
- False alerts: alert episodes (rising edges) per patient-day in non-sepsis patients.
Writes training/out/hourly_eval.json and board/sepsis-monitor/python/replay_cases.json.
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

meta = json.loads((ROOT / "training" / "out" / "meta.json").read_text())
THR = meta["threshold"]
trees = Trees(ROOT / "training" / "out" / "model.json")


def is_test(pid):
    return int(hashlib.md5(pid.encode()).hexdigest(), 16) % 1000 < 200


def carried(rows):
    last = [None] * 4
    for r in rows:
        last = [v if v is not None else l for v, l in zip(r, last)]
    return last


def run_patient(rows):
    risk, n2 = [], []
    for e in range(len(rows)):
        hist = rows[:e + 1]
        fv = features(hist)
        risk.append(None if fv is None else trees.p_sepsis(fv))
        hr, o2, t, rr = carried(hist)
        s = news2(rr=rr, spo2=o2, temp=t, hr=hr)
        n2.append((s["score"], s["any_red"]))
    return risk, n2


def episodes(flags):
    return sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))


def main():
    stats = {"sepsis": [], "healthy_hours": 0, "model_eps": 0, "news_eps": 0, "n_healthy": 0}
    candidates = []
    files = [f for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv"))) if is_test(pathlib.Path(f).stem)]
    for i, f in enumerate(files):
        df = pd.read_csv(f, sep="|", usecols=list(VITALS) + ["SepsisLabel", "Age", "Gender"])
        rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
        lab = df["SepsisLabel"].to_numpy()
        risk, n2 = run_patient(rows)
        m_flag = [r is not None and r >= THR for r in risk]
        n_flag = [k >= 8 - 1 and (s >= 5 or red) for k, (s, red) in enumerate(n2)]  # same 8 h start as model
        pid = pathlib.Path(f).stem
        if lab.max() == 1:
            onset = int(np.argmax(lab == 1)) + 6
            if onset < 8:
                continue  # positive from admission: no pre-onset window
            def first(flags):
                hits = [k for k in range(max(0, onset - 24), min(onset + 1, len(flags))) if flags[k]]
                return hits[0] if hits else None
            fm, fn = first(m_flag), first(n_flag)
            stats["sepsis"].append({"pid": pid, "onset": onset, "model_lead": None if fm is None else onset - fm,
                                    "news_lead": None if fn is None else onset - fn})
            w0 = max(0, onset - 30)  # the replay shows hours w0 .. onset+4
            clean_before = fm is not None and not any(m_flag[w0:fm]) and not any(n_flag[w0:fm + 3])
            if onset >= 30 and fm is not None and onset - fm >= 4 and (fn is None or fn > fm + 2) and clean_before:
                candidates.append(("sepsis", pid, onset - fm, rows, lab, risk, n2, onset, df))
        else:
            stats["n_healthy"] += 1
            stats["healthy_hours"] += max(0, len(rows) - 7)
            stats["model_eps"] += episodes(m_flag)
            stats["news_eps"] += episodes(n_flag)
            if len(rows) >= 40 and not any(m_flag) and not any(n_flag):
                candidates.append(("healthy", pid, 0, rows, lab, risk, n2, None, df))
        if i % 1000 == 0:
            print("patients", i, "/", len(files), flush=True)

    s = stats["sepsis"]
    days = stats["healthy_hours"] / 24
    res = {
        "threshold": THR,
        "n_sepsis_patients": len(s), "n_nonsepsis_patients": stats["n_healthy"],
        "model": {"flagged_before_onset": float(np.mean([x["model_lead"] is not None for x in s])),
                  "median_lead_h": float(np.median([x["model_lead"] for x in s if x["model_lead"] is not None])),
                  "false_alert_episodes_per_patient_day": stats["model_eps"] / days},
        "news2_rule": {"flagged_before_onset": float(np.mean([x["news_lead"] is not None for x in s])),
                       "median_lead_h": float(np.median([x["news_lead"] for x in s if x["news_lead"] is not None])),
                       "false_alert_episodes_per_patient_day": stats["news_eps"] / days},
        "model_earlier_than_news2": float(np.mean([x["model_lead"] is not None and (x["news_lead"] is None or x["model_lead"] > x["news_lead"]) for x in s])),
    }
    print(json.dumps(res, indent=1))
    (ROOT / "training" / "out" / "hourly_eval.json").write_text(json.dumps(res, indent=1))

    def pack(c):
        kind, pid, lead, rows, lab, risk, n2, onset, df = c
        return {"id": pid, "kind": kind, "age": None if pd.isna(df["Age"].iloc[0]) else float(df["Age"].iloc[0]),
                "label": "Recorded ICU case (PhysioNet 2019, held out), accelerated",
                "onset_hour": onset, "first_label_hour": None if onset is None else onset - 6,
                "start_hour": 8 if onset is None else max(8, onset - 30),
                "end_hour": min(len(rows) - 1, 8 + 34) if onset is None else min(len(rows) - 1, onset + 4),
                "vitals": rows, "sepsis_label": [int(x) for x in lab],
                "expected_risk": [None if r is None else round(r * 100, 1) for r in risk],
                "expected_news2": [x[0] for x in n2]}

    sep = sorted([c for c in candidates if c[0] == "sepsis"], key=lambda c: -c[2])
    hea = [c for c in candidates if c[0] == "healthy"]
    # median-ish lead among qualifying cases, not the most extreme one
    chosen = [sep[len(sep) // 2]] if sep else []
    chosen += [hea[0]] if hea else []
    out = {"note": "Held-out PhysioNet 2019 patients, never used for training. The sepsis case was chosen from "
                   f"{len(sep)} qualifying cases (model alerted 4+ h before onset, neither method alerted earlier in the 30 h shown) as the median lead, "
                   "so it is illustrative, not typical. See hourly_eval.json for the whole test set.",
           "threshold": round(THR * 100, 1), "cases": [pack(c) for c in chosen]}
    (ROOT / "board" / "sepsis-monitor" / "python" / "replay_cases.json").write_text(json.dumps(out))
    for c in chosen:
        print("replay case", c[0], c[1], "lead", c[2], "hours", len(c[3]))


if __name__ == "__main__":
    main()
