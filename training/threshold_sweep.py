"""Model catch rate vs false-alert burden across thresholds, on all held-out test patients.
Answers: at the SAME false-alert rate as the 4-vital NEWS2 rule, how many sepsis patients does the model flag?"""
import glob, json, pathlib, sys
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from replay_select import ROOT, VITALS, is_test, run_patient, episodes

THRS = [0.40, 0.45, 0.50, 0.52, 0.55, 0.58, 0.614, 0.65]
seps, heal_hours, eps = [], 0, {t: 0 for t in THRS}
files = [f for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv"))) if is_test(pathlib.Path(f).stem)]
for f in files:
    df = pd.read_csv(f, sep="|", usecols=list(VITALS) + ["SepsisLabel"])
    rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
    lab = df["SepsisLabel"].to_numpy()
    risk, _ = run_patient(rows)
    r = np.array([-1 if x is None else x for x in risk])
    if lab.max() == 1:
        onset = int(np.argmax(lab == 1)) + 6
        if onset >= 8:
            seps.append((r, onset))
    else:
        heal_hours += max(0, len(rows) - 7)
        for t in THRS:
            eps[t] += episodes(list(r >= t))
out = []
for t in THRS:
    caught = np.mean([(r[max(0, o - 24):o + 1] >= t).any() for r, o in seps])
    out.append({"threshold": t, "flagged_before_onset": round(float(caught), 3),
                "false_alerts_per_patient_day": round(eps[t] / (heal_hours / 24), 2)})
print(json.dumps(out, indent=1))
(ROOT / "training" / "out" / "threshold_sweep.json").write_text(json.dumps(out, indent=1))
