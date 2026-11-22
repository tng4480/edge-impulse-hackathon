"""What-if stress lab: perturb a recorded ICU case and re-score it hour by hour.

Every scenario is a simulated stressor applied to recorded PhysioNet 2019 vitals. It shows how
the model and the NEWS2 rule shift; it is not a validated correction for any of these effects.

    scenarios() -> [{"id", "title", "description", "label", "applies_to"}]
    run(case, "spo2_overread_4", risk_model) -> {"timeline": [...], "summary": {"model": {...}, "news2": {...}}, ...}

`case` is a dict from replay_cases.json (load_cases() returns them by id). `risk_model` is a
model_runner.RiskModel (.eim or the Trees fallback, whichever it picked). The same perturb() and
news2_flag() are used by training/stress_eval.py, so the board and the offline evaluation agree.
"""
import json
import pathlib

from features import DEFAULTS, MIN_HOURS
from news2 import news2

HERE = pathlib.Path(__file__).parent
LABEL = "Simulated stressor on a recorded ICU case"
HR, SPO2, TEMP, RR = 0, 1, 2, 3          # column order of an hourly row: [HR, O2Sat, Temp, Resp]
SPARSE_EVERY_H = 4
BETA_BLOCKER_HR_CAP = 80.0
WALK_HR, WALK_RR, WALK_HOURS = 25.0, 6.0, 2

_SJODING = ("Sjoding et al., N Engl J Med 2020;383:2477-8, doi 10.1056/NEJMc2029240, found occult hypoxaemia "
            "(arterial SaO2 below 88 % while the oximeter read 92-96 %) about three times as often in Black "
            "as in White patients.")

_SCENARIOS = [
    ("baseline", "Baseline", "The recorded vitals, unchanged.", ("sepsis", "healthy")),
    ("spo2_overread_2", "SpO2 over-read +2",
     "Every SpO2 reading is raised by 2 points (capped at 100), to illustrate pulse-oximeter over-reading in "
     "darker skin. " + _SJODING + " The fixed offset is an illustration, not a correction factor.", ("sepsis", "healthy")),
    ("spo2_overread_4", "SpO2 over-read +4",
     "Every SpO2 reading is raised by 4 points (capped at 100), to illustrate pulse-oximeter over-reading in "
     "darker skin. " + _SJODING + " The fixed offset is an illustration, not a correction factor.", ("sepsis", "healthy")),
    ("spo2_missing", "No SpO2",
     "All SpO2 readings removed, as when the watch's spot reading fails. NEWS2 scores without its SpO2 item; "
     "the model falls back to the population median (98 %).", ("sepsis", "healthy")),
    ("spo2_sparse", "SpO2 every 4 h",
     f"SpO2 kept only at hours divisible by {SPARSE_EVERY_H} (and only where one was recorded); both methods "
     "carry the last reading forward in between.", ("sepsis", "healthy")),
    ("beta_blocker", "Beta-blocker (HR capped at 80)",
     f"Heart rate capped at {BETA_BLOCKER_HR_CAP:.0f} bpm, as a beta-blocker blunts the tachycardia of sepsis.",
     ("sepsis", "healthy")),
    ("walk_burst", "Walk burst (non-sepsis)",
     f"Heart rate +{WALK_HR:.0f} bpm and respiratory rate +{WALK_RR:.0f} breaths/min for {WALK_HOURS} consecutive "
     "hours, an exertion artefact with no infection. Applied to non-sepsis cases only, as a false-alarm test.",
     ("healthy",)),
    ("temp_missing", "No core temperature",
     "All temperature readings removed, the live wearable reality (the watch measures wrist skin, not core). "
     "NEWS2 scores without its temperature item; the model falls back to the median (36.9 °C).", ("sepsis", "healthy")),
]
SCENARIO_IDS = [s[0] for s in _SCENARIOS]


def scenarios():
    return [{"id": i, "title": t, "description": d, "label": LABEL, "applies_to": list(a)} for i, t, d, a in _SCENARIOS]


def load_cases(path=HERE / "replay_cases.json"):
    return {c["id"]: c for c in json.loads(pathlib.Path(path).read_text())["cases"]}


def walk_hours(n, start=None, end=None):
    """The 2 burst hours: the middle of [start, end] (the shown window), else of the record, never before MIN_HOURS."""
    lo = MIN_HOURS if start is None else max(MIN_HOURS, start)
    hi = n - 1 if end is None else min(end, n - 1)
    b = max(lo, (lo + hi) // 2)
    return [h for h in range(b, b + WALK_HOURS) if h < n]


def perturb(rows, scenario, burst=None):
    """Return a perturbed copy of hourly rows [[HR, O2Sat, Temp, Resp], ...]; None stays None unless noted.
    burst: hours for walk_burst (default walk_hours(len(rows)))."""
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario!r}")
    out = [list(r) for r in rows]
    if scenario.startswith("spo2_overread_"):
        d = float(scenario.rsplit("_", 1)[1])
        for r in out:
            if r[SPO2] is not None:
                r[SPO2] = min(100.0, r[SPO2] + d)
    elif scenario == "spo2_missing":
        for r in out:
            r[SPO2] = None
    elif scenario == "spo2_sparse":
        for h, r in enumerate(out):
            if h % SPARSE_EVERY_H:
                r[SPO2] = None
    elif scenario == "beta_blocker":
        for r in out:
            if r[HR] is not None:
                r[HR] = min(BETA_BLOCKER_HR_CAP, r[HR])
    elif scenario == "temp_missing":
        for r in out:
            r[TEMP] = None
    elif scenario == "walk_burst":
        burst = walk_hours(len(out)) if burst is None else burst
        last = [None] * 4
        for h, r in enumerate(out):
            if h in burst:   # exertion on top of the value the wearer would otherwise show (carried forward)
                hr = rows[h][HR] if rows[h][HR] is not None else (last[HR] if last[HR] is not None else DEFAULTS["HR"])
                rr = rows[h][RR] if rows[h][RR] is not None else (last[RR] if last[RR] is not None else DEFAULTS["Resp"])
                r[HR], r[RR] = hr + WALK_HR, rr + WALK_RR
            last = [v if v is not None else l for v, l in zip(rows[h], last)]
    return out


def news2_at(hist):
    """NEWS2 on values carried forward to the last hour, as replay.py does. Returns (score, alert)."""
    last = [None] * 4
    for r in hist:
        last = [v if v is not None else l for v, l in zip(r, last)]
    s = news2(hr=last[HR], spo2=last[SPO2], temp=last[TEMP], rr=last[RR])
    return s["score"], s["score"] >= 5 or s["any_red"]


def _method_summary(tl, key, onset):
    alerts = [p["hour"] for p in tl if p[key]]
    first = alerts[0] if alerts else None
    pre = [h for h in alerts if onset is not None and onset - 24 <= h <= onset - 1]
    eps = sum(1 for i, p in enumerate(tl) if p[key] and (i == 0 or not tl[i - 1][key]))
    return {"first_alert_hour": first,
            "warning_hours_before_onset": (onset - pre[0]) if pre else None,   # strict window onset-24..onset-1
            "hours_in_alert": len(alerts), "alert_episodes": eps}


_cache = {}


def run(case, scenario, model):
    """Perturb `case` and re-score the shown hours (start_hour..end_hour) with `model` (a RiskModel)."""
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario!r}")
    kind = "healthy" if case.get("onset_hour") is None else "sepsis"
    applies = dict((s[0], s[3]) for s in _SCENARIOS)[scenario]
    if kind not in applies:
        raise ValueError(f"scenario {scenario!r} applies only to {' and '.join(applies)} cases")
    key = (case["id"], scenario, getattr(model, "name", type(model).__name__))
    if key in _cache:
        return _cache[key]
    rows = case["vitals"]
    n = len(rows)
    start, end = case.get("start_hour", 0), case.get("end_hour", n - 1)
    burst = walk_hours(n, start, end) if scenario == "walk_burst" else []
    stressed = perturb(rows, scenario, burst=burst or None)
    onset = case.get("onset_hour")
    tl = []
    for h in range(start, end + 1):
        hist = stressed[:h + 1]
        r = model.score(hist)
        n2, n2_alert = news2_at(hist)
        tl.append({"hour": h, "risk": r["risk"], "model_alert": bool(r["alert"]), "news2": n2, "news2_alert": n2_alert,
                   "vitals": stressed[h], "changed": stressed[h] != list(rows[h])})
    out = {
        "case": case["id"], "kind": kind, "scenario": scenario, "label": LABEL,
        "title": next(s["title"] for s in scenarios() if s["id"] == scenario),
        "onset_hour": onset, "start_hour": start, "end_hour": end,
        "threshold": round(model.threshold * 100, 1), "engine": getattr(model, "name", "?"),
        "burst_hours": burst,
        "timeline": tl,
        "summary": {"model": _method_summary(tl, "model_alert", onset), "news2": _method_summary(tl, "news2_alert", onset)},
    }
    _cache[key] = out
    return out


# ---- HTTP helpers for main.py: each returns (status_code, json_payload) -------------------------

_CASES = None


def api_stress(query, model):
    """GET /api/stress?case=&scenario=. query: dict of str (or of 1-item lists, as parse_qs gives).
    No case and no scenario -> the catalogue of cases and scenarios."""
    global _CASES
    if _CASES is None:
        _CASES = load_cases()
    q = {k: (v[0] if isinstance(v, list) else v) for k, v in query.items()}
    case_id, sc = q.get("case"), q.get("scenario")
    if not case_id and not sc:
        return 200, {"label": LABEL, "scenarios": scenarios(), "cases": [
            {"id": c["id"], "kind": c["kind"], "label": c["label"], "onset_hour": c["onset_hour"],
             "start_hour": c.get("start_hour", 0), "end_hour": c.get("end_hour", len(c["vitals"]) - 1)}
            for c in _CASES.values()]}
    if case_id not in _CASES:
        return 404, {"ok": False, "error": f"unknown case {case_id!r}"}
    try:
        return 200, run(_CASES[case_id], sc or "baseline", model)
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}


def api_summary(path=HERE / "model" / "stress_eval.json"):
    """GET /api/stress/summary: the whole-test-set results from training/stress_eval.py."""
    p = pathlib.Path(path)
    if not p.exists():
        return 404, {"ok": False, "error": "model/stress_eval.json not found; run training/stress_eval.py"}
    return 200, json.loads(p.read_text())
