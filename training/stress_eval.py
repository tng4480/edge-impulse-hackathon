"""Stress lab across ALL held-out test patients (md5 split from strict_eval.py).

Each scenario in board/.../stress.py is applied to every test patient's hourly vitals, then the model
(Trees on training/out/model.json at the device threshold in board/.../model/meta.json) and the NEWS2
rule (5+ or any single 3, values carried forward) are re-scored hour by hour, exactly as in
strict_eval.py. walk_burst is applied to non-sepsis patients only (a false-alarm test).

Writes training/out/stress_eval.json, board/sepsis-monitor/python/model/stress_eval.json (copy served
at /api/stress/summary) and docs/stress_results.md.

    .venv/Scripts/python.exe training/stress_eval.py [--limit N] [--procs P]
"""
import argparse
import glob
import json
import multiprocessing as mp
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOARD = ROOT / "board" / "sepsis-monitor" / "python"
sys.path.insert(0, str(BOARD))
from features import VITALS, features  # noqa: E402
from model_runner import Trees  # noqa: E402
import stress  # noqa: E402

MODEL_JSON = ROOT / "training" / "out" / "model.json"
THRESHOLD = json.loads((BOARD / "model" / "meta.json").read_text())["threshold"]
_trees = None


def group(pid):  # identical to strict_eval.group, copied so importing it does not load a second model
    import hashlib
    h = lambda p, salt="": int(hashlib.md5((salt + p).encode()).hexdigest(), 16) % 1000  # noqa: E731
    if h(pid) < 200:
        return "test"
    return "val" if h(pid, "val") < 100 else "train"


def score(rows):
    """Per hour: model probability (-1 before MIN_HOURS) and the NEWS2 rule flag (same 8 h start)."""
    risk, n2 = np.full(len(rows), -1.0), np.zeros(len(rows), bool)
    for e in range(len(rows)):
        hist = rows[:e + 1]
        fv = features(hist)
        if fv is not None:
            risk[e] = _trees.p_sepsis(fv)
            n2[e] = stress.news2_at(hist)[1]
    return risk, n2


def work(path):
    global _trees
    if _trees is None:
        _trees = Trees(MODEL_JSON)
    df = pd.read_csv(path, sep="|", usecols=list(VITALS) + ["SepsisLabel"])
    rows = [[None if pd.isna(v) else float(v) for v in r] for r in df[list(VITALS)].itertuples(index=False)]
    lab = df["SepsisLabel"].to_numpy()
    sepsis = bool(lab.max() == 1)
    onset = int(np.argmax(lab == 1)) + 6 if sepsis else None
    if sepsis and onset < 9:   # strict_eval: need at least one scorable hour before onset
        return None
    out = {}
    for sc in stress.SCENARIO_IDS:
        if sc == "walk_burst" and sepsis:
            continue
        out[sc] = score(stress.perturb(rows, sc))
    return {"pid": pathlib.Path(path).stem, "sepsis": sepsis, "onset": onset, "res": out}


def episodes(f):
    f = np.asarray(f, bool)
    return int(f[0]) + int((f[1:] & ~f[:-1]).sum()) if len(f) else 0


def metrics(pats, sc, model):
    flag = (lambda r, n: r >= THRESHOLD) if model else (lambda r, n: n)
    caught, leads, hours, eps, on = [], [], 0, 0, 0
    for p in pats:
        if sc not in p["res"]:
            continue
        r, n = p["res"][sc]
        f = flag(r, n)
        if p["sepsis"]:
            o = p["onset"]
            w = f[max(0, o - 24):o]
            caught.append(bool(w.any()))
            if w.any():
                leads.append(len(w) - int(np.argmax(w)))
        else:
            ok = r >= 0
            hours += int(ok.sum())
            eps += episodes(f[ok])
            on += int(f[ok].sum())
    return {"flagged_before_onset": round(float(np.mean(caught)), 3) if caught else None,
            "false_alerts_per_patient_day": round(eps / (hours / 24), 2) if hours else None,
            "nonsepsis_hours_in_alert": round(on / hours, 3) if hours else None,
            "median_first_alert_hours_before_onset": float(np.median(leads)) if leads else None}


def pct(x):
    return "n/a" if x is None else f"{x * 100:.0f} %"


def num(x):
    return "n/a" if x is None else f"{x:.2f}"


def delta(a, b, scale=100, unit=" pts"):
    if a is None or b is None:
        return ""
    d = (a - b) * scale
    if scale == 100:
        return f" ({'±0' if round(d) == 0 else f'{d:+.0f}'}{unit})"
    return f" ({'±0' if round(d, 2) == 0 else f'{d:+.2f}'})"


def verdict(sc, base, cur):
    if sc == "baseline":
        return "Reference."
    bm, bn, m, n = base["model"], base["news2"], cur["model"], cur["news2"]
    parts = []
    if m["flagged_before_onset"] is not None:
        dm = m["flagged_before_onset"] - bm["flagged_before_onset"]
        dn = n["flagged_before_onset"] - bn["flagged_before_onset"]
        if abs(dm) < 0.005 and abs(dn) < 0.005:
            parts.append("catch rate unchanged for both")
        else:
            worse = "the model" if dm < dn else "NEWS2" if dn < dm else "neither more than the other"
            parts.append(f"catch rate: model {dm * 100:+.0f} pts, NEWS2 {dn * 100:+.0f} pts, so {worse} loses more")
    fm = m["false_alerts_per_patient_day"] - bm["false_alerts_per_patient_day"]
    fn = n["false_alerts_per_patient_day"] - bn["false_alerts_per_patient_day"]
    hm = (m["nonsepsis_hours_in_alert"] - bm["nonsepsis_hours_in_alert"]) * 100
    hn = (n["nonsepsis_hours_in_alert"] - bn["nonsepsis_hours_in_alert"]) * 100
    parts.append(f"false alerts/day: model {fm:+.2f}, NEWS2 {fn:+.2f}; alarm time: model {hm:+.1f} pts, NEWS2 {hn:+.1f} pts")
    return "; ".join(parts) + "."


def write_md(res):
    sc_by = {s["id"]: s for s in res["scenarios"]}
    base = sc_by["baseline"]
    L = ["# Stress lab results (simulated stressors on recorded ICU data)", "",
         f"Every row applies a **simulated stressor** to the recorded vitals of all held-out test patients "
         f"({res['n_sepsis']} sepsis, {res['n_nonsepsis']} non-sepsis; md5 split as in `training/strict_eval.py`) "
         f"and re-scores them hour by hour. Model: LightGBM trees at the device cutoff {res['threshold']}. "
         "NEWS2 rule: 4-vital score 5+ or any single 3, values carried forward. "
         "Flagged = an alert in hours onset−24 to onset−1 (onset = first SepsisLabel hour + 6). "
         "False alerts = separate alert episodes per patient-day in non-sepsis patients. "
         "Generated by `training/stress_eval.py`; raw numbers in `training/out/stress_eval.json`.", "",
         "These are illustrations of failure modes, not corrections. The SpO2 over-read rows illustrate the "
         "bias reported by Sjoding et al., NEJM 2020 (doi 10.1056/NEJMc2029240) with a fixed offset; real "
         "over-reading varies by device and patient.", "",
         "| Scenario | Model flagged | NEWS2 flagged | Model false alerts/day | NEWS2 false alerts/day | Model alarm time | NEWS2 alarm time |",
         "|---|---|---|---|---|---|---|"]
    for s in res["scenarios"]:
        m, n = s["model"], s["news2"]
        bm, bn = base["model"], base["news2"]
        L.append(f"| {s['title']} | {pct(m['flagged_before_onset'])}{delta(m['flagged_before_onset'], bm['flagged_before_onset'])}"
                 f" | {pct(n['flagged_before_onset'])}{delta(n['flagged_before_onset'], bn['flagged_before_onset'])}"
                 f" | {num(m['false_alerts_per_patient_day'])}{delta(m['false_alerts_per_patient_day'], bm['false_alerts_per_patient_day'], 1)}"
                 f" | {num(n['false_alerts_per_patient_day'])}{delta(n['false_alerts_per_patient_day'], bn['false_alerts_per_patient_day'], 1)}"
                 f" | {pct(m['nonsepsis_hours_in_alert'])}{delta(m['nonsepsis_hours_in_alert'], bm['nonsepsis_hours_in_alert'])}"
                 f" | {pct(n['nonsepsis_hours_in_alert'])}{delta(n['nonsepsis_hours_in_alert'], bn['nonsepsis_hours_in_alert'])} |")
    L += ["", "Brackets: change from baseline (percentage points, or alerts per day). "
          "`n/a` for walk burst catch rate: it is applied to non-sepsis patients only.", "",
          "## Reading it honestly", "",
          "- **Missing core temperature hurts the model most.** It is the live wearable situation (the watch reads wrist "
          "skin, not core), and the model's catch rate falls far more than the NEWS2 rule's. Its fewer false alerts come "
          "from the same lost signal, so they are not a gain. On the device the model gets an estimated core temperature "
          "(wrist skin plus a fixed offset), so real performance probably sits between the baseline and this row, "
          "but that is not measured here.",
          "- **A beta-blocker hurts the model more than NEWS2.** The model leans on heart-rate trends, and capping HR at "
          "80 bpm removes them.",
          "- **SpO2 over-reading hurts NEWS2.** Its SpO2 item scores fewer points, so it catches fewer sepsis cases "
          "(the safety risk Sjoding et al. describe). The model's catch rate does not fall and its alarm time rises. This is "
          "**not** robustness: the model seems to treat SpO2 near 100 % as a risk marker, probably an ICU artefact "
          "(patients on supplemental oxygen). Neither method corrects the bias; the fixed offset is an illustration.",
          "- **Missing or sparse SpO2** costs both methods a similar amount.",
          "- **A 2-hour walk** adds false alerts for both. NEWS2 adds more separate alerts per day and both add about "
          "the same alarm time. The device's motion context should suppress or label these.",
          "", "## Which method degrades more (auto-generated)", ""]
    for s in res["scenarios"]:
        L.append(f"- **{s['title']}:** {s['verdict']}")
    (ROOT / "docs" / "stress_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="first N test patients only (smoke test)")
    ap.add_argument("--procs", type=int, default=max(1, mp.cpu_count() - 2))
    a = ap.parse_args()
    files = [f for f in sorted(glob.glob(str(ROOT / "data" / "raw" / "[AB]" / "p*.psv"))) if group(pathlib.Path(f).stem) == "test"]
    if a.limit:
        files = files[:a.limit]
    print(f"{len(files)} test files, {a.procs} processes, threshold {THRESHOLD}", flush=True)
    t0, pats = time.time(), []
    with mp.Pool(a.procs) as pool:
        for i, p in enumerate(pool.imap_unordered(work, files, chunksize=8)):
            if p is not None:
                pats.append(p)
            if (i + 1) % 500 == 0:
                print(f"{i + 1}/{len(files)} {time.time() - t0:.0f}s", flush=True)
    n_s = sum(p["sepsis"] for p in pats)
    res = {"definition": "alerts in the 24 h strictly before onset (onset = first SepsisLabel + 6 h); false alerts = "
                         "alert episodes per patient-day in non-sepsis patients; NEWS2 rule = 5+ or any single 3",
           "label": stress.LABEL, "threshold": THRESHOLD, "model": "Trees(training/out/model.json)",
           "n_sepsis": n_s, "n_nonsepsis": len(pats) - n_s, "limit": a.limit or None, "scenarios": []}
    base = None
    for s in stress.scenarios():
        row = {"id": s["id"], "title": s["title"], "applies_to": s["applies_to"],
               "model": metrics(pats, s["id"], True), "news2": metrics(pats, s["id"], False)}
        base = base or row
        row["verdict"] = verdict(s["id"], base, row)
        res["scenarios"].append(row)
        print(s["id"], json.dumps(row["model"]), json.dumps(row["news2"]), flush=True)
    txt = json.dumps(res, indent=1)
    (ROOT / "training" / "out" / "stress_eval.json").write_text(txt)
    (BOARD / "model" / "stress_eval.json").write_text(txt)
    write_md(res)
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
