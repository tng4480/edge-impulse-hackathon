"""Alert-policy search (device-realistic: no temperature, model v3 vs 3-vital NEWS2).

The model's score is sticky (24 h aggregates), so a bare cutoff keeps alarms on for long after the
rise. A policy with hysteresis can shorten alarms: turn ON after k consecutive hours >= t_on, turn
OFF as soon as the score falls below t_off (t_off <= t_on) or after max_len hours.
Policies are chosen on VALIDATION patients only, under the constraint that the share of non-sepsis
hours in alert is no higher than the 3-vital NEWS2 rule's on validation; then reported once on test.
Output: training/out/policy_eval.json.   Run: python training/policy_eval.py
"""
import itertools
import json
import os
import pathlib
import pickle
import sys

os.environ["MASK_TEMP"] = "1"
os.environ.setdefault("MODEL_JSON", str(pathlib.Path(__file__).resolve().parent / "out" / "v3" / "model.json"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import strict_eval as se  # noqa: E402

ROOT = se.ROOT
CACHE = ROOT / "training" / "out" / "policy_cache.pkl"


def load():
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    data = {w: se.collect(w) for w in ("val", "test")}
    CACHE.write_bytes(pickle.dumps(data))
    return data


def apply(r, t_on, t_off, k, max_len):
    """Alert flags for one risk series. r = -1 where unscored."""
    out = np.zeros(len(r), bool)
    on, run, held = False, 0, 0
    for i, v in enumerate(r):
        if v < 0:
            on, run, held = False, 0, 0
            continue
        if not on:
            run = run + 1 if v >= t_on else 0
            if run >= k:
                on, held = True, 0
        else:
            held += 1
            if v < t_off or held >= max_len:
                on, run = False, 0
        out[i] = on
    return out


def evaluate(seps, heal, flagger):
    caught, leads = [], []
    for r, n, o in seps:
        w = flagger(r, n)[max(0, o - 24):o]
        caught.append(bool(w.any()))
        if w.any():
            leads.append(len(w) - int(np.argmax(w)))
    hours = sum(int((r >= 0).sum()) for r, n in heal)
    eps = on = 0
    for r, n in heal:
        f = flagger(r, n)[r >= 0]
        on += int(f.sum())
        eps += se.episodes(f)
    return {"flagged_before_onset": round(float(np.mean(caught)), 3),
            "false_alerts_per_patient_day": round(eps / (hours / 24), 2),
            "nonsepsis_hours_in_alert": round(on / hours, 3),
            "median_first_alert_hours_before_onset": float(np.median(leads)) if leads else None}


def main():
    data = load()
    (vs, vh), (ts, th) = data["val"], data["test"]
    news = lambda r, n: n
    n2_val, n2_test = evaluate(vs, vh, news), evaluate(ts, th, news)
    print("NEWS2 3-vital  val", n2_val, "\n               test", n2_test, flush=True)
    budget = n2_val["nonsepsis_hours_in_alert"]
    rows = []
    for t_on, gap, k, max_len in itertools.product(np.arange(0.40, 0.86, 0.03), (0, 0.06, 0.12, 0.2), (1, 2, 3), (6, 12, 24, 999)):
        t_on = round(float(t_on), 2)
        t_off = round(t_on - gap, 2)
        fl = lambda r, n, a=(t_on, t_off, k, max_len): apply(r, *a)
        m = evaluate(vs, vh, fl)
        rows.append({"policy": {"t_on": t_on, "t_off": t_off, "k": k, "max_len": max_len}, **m})
    ok = [x for x in rows if x["nonsepsis_hours_in_alert"] <= budget]
    ok.sort(key=lambda x: -x["flagged_before_onset"])
    best = ok[0] if ok else None
    # also best when matching NEWS2's separate alerts per day
    ok2 = [x for x in rows if x["false_alerts_per_patient_day"] <= n2_val["false_alerts_per_patient_day"]
           and x["nonsepsis_hours_in_alert"] <= 1.5 * budget]
    ok2.sort(key=lambda x: -x["flagged_before_onset"])
    best2 = ok2[0] if ok2 else None
    plain = [x for x in rows if x["policy"]["t_off"] == x["policy"]["t_on"] and x["policy"]["k"] == 1 and x["policy"]["max_len"] == 999
             and x["nonsepsis_hours_in_alert"] <= budget]
    plain.sort(key=lambda x: -x["flagged_before_onset"])
    res = {"definition": "val-chosen policies; device-realistic (no temperature); NEWS2 on HR, SpO2, RR",
           "validation_budget_hours_in_alert": budget, "news2_val": n2_val, "news2_test": n2_test}
    for name, pick in (("bare_cutoff_equal_alarm_time", plain[0] if plain else None),
                       ("best_policy_equal_alarm_time", best),
                       ("best_policy_equal_separate_alerts", best2)):
        if pick:
            p = pick["policy"]
            res[name] = {"policy": p, "validation": {k: v for k, v in pick.items() if k != "policy"},
                         "test": evaluate(ts, th, lambda r, n, a=(p["t_on"], p["t_off"], p["k"], p["max_len"]): apply(r, *a))}
            print(name, json.dumps(res[name]), flush=True)
    (ROOT / "training" / "out" / "policy_eval.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
