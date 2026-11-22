"""Tests for stress.py.  Run: .venv/Scripts/python.exe -m pytest board/sepsis-monitor/python/test_stress.py
(or run this file directly)."""
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import stress  # noqa: E402
from features import FEATURE_NAMES, features  # noqa: E402
from model_runner import Trees  # noqa: E402
import json  # noqa: E402

CASES = stress.load_cases()
SEP, HEALTHY = CASES["p112060"], CASES["p000147"]
HR, O2, T, RR = 0, 1, 2, 3


class TreesModel:
    """RiskModel-shaped wrapper around the pure-Python trees (no .eim needed on a laptop)."""
    name = "trees"

    def __init__(self):
        self.engine = Trees(HERE / "model" / "model.json")
        self.threshold = json.loads((HERE / "model" / "meta.json").read_text())["threshold"]

    def score(self, hourly):
        fv = features(hourly)
        if fv is None:
            return {"risk": None, "alert": False}
        p = self.engine.p_sepsis(fv)
        return {"risk": round(p * 100, 1), "alert": p >= self.threshold}


def col(rows, i):
    return [r[i] for r in rows]


def same_except(a, b, cols):
    keep = [i for i in range(4) if i not in cols]
    return all(col(a, i) == col(b, i) for i in keep)


def test_baseline_matches_replay_expected_risk():
    out = stress.run(SEP, "baseline", TreesModel())
    exp = SEP["expected_risk"]
    checked = 0
    for p in out["timeline"]:
        if exp[p["hour"]] is not None:
            assert p["risk"] is not None and abs(p["risk"] - exp[p["hour"]]) <= 0.1, (p["hour"], p["risk"], exp[p["hour"]])
            checked += 1
        assert p["news2"] == SEP["expected_news2"][p["hour"]]
    assert checked >= 30
    assert out["label"] == stress.LABEL
    assert out["summary"]["model"]["warning_hours_before_onset"] == 24   # docs/results.md: alerts at hour 89, onset 113


def test_overread_changes_only_spo2_and_caps_at_100():
    v = SEP["vitals"]
    for d in (2, 4):
        p = stress.perturb(v, f"spo2_overread_{d}")
        assert same_except(p, v, [O2])
        for a, b in zip(col(p, O2), col(v, O2)):
            assert (a is None) == (b is None)
            if b is not None:
                assert a == min(100.0, b + d)
    assert v[0][O2] == 95.0   # input untouched


def test_spo2_missing_and_sparse():
    v = SEP["vitals"]
    p = stress.perturb(v, "spo2_missing")
    assert same_except(p, v, [O2]) and all(x is None for x in col(p, O2))
    p = stress.perturb(v, "spo2_sparse")
    assert same_except(p, v, [O2])
    for h, (a, b) in enumerate(zip(col(p, O2), col(v, O2))):
        assert a == (b if h % 4 == 0 else None)


def test_beta_blocker_caps_hr_only():
    v = SEP["vitals"]
    p = stress.perturb(v, "beta_blocker")
    assert same_except(p, v, [HR])
    for a, b in zip(col(p, HR), col(v, HR)):
        assert a == (None if b is None else min(80.0, b))
    assert any(b is not None and b > 80 for b in col(v, HR))   # the cap actually bites on this case


def test_temp_missing():
    v = SEP["vitals"]
    p = stress.perturb(v, "temp_missing")
    assert same_except(p, v, [T]) and all(x is None for x in col(p, T))


def test_walk_burst_two_hours_hr_rr_only():
    v = HEALTHY["vitals"]
    burst = stress.walk_hours(len(v), HEALTHY["start_hour"], HEALTHY["end_hour"])
    assert len(burst) == 2 and HEALTHY["start_hour"] <= burst[0] <= HEALTHY["end_hour"]
    p = stress.perturb(v, "walk_burst", burst=burst)
    assert same_except(p, v, [HR, RR])
    changed = [h for h in range(len(v)) if p[h] != v[h]]
    assert changed == burst
    for h in burst:
        assert p[h][HR] >= 25 + 40 and p[h][RR] >= 6   # +25 bpm / +6 on a real (carried) value


def test_walk_burst_rejected_on_sepsis_case_and_unknown_scenario():
    for sc, case in (("walk_burst", SEP), ("nope", HEALTHY)):
        try:
            stress.run(case, sc, TreesModel())
        except ValueError:
            continue
        raise AssertionError(f"{sc} should be rejected")


def test_every_scenario_runs_and_is_labelled():
    m = TreesModel()
    ids = [s["id"] for s in stress.scenarios()]
    assert ids == ["baseline", "spo2_overread_2", "spo2_overread_4", "spo2_missing", "spo2_sparse",
                   "beta_blocker", "walk_burst", "temp_missing"]
    for s in stress.scenarios():
        assert s["label"] == "Simulated stressor on a recorded ICU case"
        case = HEALTHY if s["id"] == "walk_burst" else SEP
        out = stress.run(case, s["id"], m)
        assert len(out["timeline"]) == case["end_hour"] - case["start_hour"] + 1
        assert set(out["summary"]) == {"model", "news2"}
    assert "10.1056/NEJMc2029240" in next(s for s in stress.scenarios() if s["id"] == "spo2_overread_2")["description"]


if __name__ == "__main__":
    fns = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
