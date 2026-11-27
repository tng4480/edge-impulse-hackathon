"""Sepsis monitor: Linux side of the UNO Q app.

- pulls chest-IMU samples from the STM32 each second and estimates respiratory rate
- accepts the watch's vitals at POST /vitals (contract in board/README.md)
- merges watch / IMU / dashboard overrides into one "current vitals" record
- scores it (partial NEWS2 for now; the Edge Impulse model plugs in at risk_from_model)
- buzzes the Vibro on a sustained high score and serves the dashboard on port 8000
"""
import json
import pathlib
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from arduino.app_utils import App, Bridge

from urllib.parse import parse_qs, urlparse

import fhir
import handoff as handoff_mod
import pathways
from liveness import (ENGINE_OK_S, REST_MOTION_G, WATCH_LOST_S, WATCH_OK_S, Baseline, Faults, NetCheck,
                      age_info)
from model_runner import HourlyVitals, RiskModel
from news2 import news2
from replay import Replay
from resp import FS, estimate_rr, motion_level
from rigor import RigorDetector
import pat as pat_mod
import stress

HERE = pathlib.Path(__file__).parent
PORT = 8000
LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()   # the .eim runner is one process: one scoring call at a time
MODEL_EVERY_S = 5               # live model re-score interval

HR_FRESH_S = 30         # watch hr older than this is treated as missing
TEMP_FRESH_S = 180      # watch reads skin temp about once a minute; hold the last good one for 3 minutes
# Wrist skin temperature is NOT core temperature: it can even fall at fever onset (vasoconstriction),
# so it is never fed to NEWS2 or the model. We show it against the wearer's own baseline instead.
SKIN_BASE_NEWEST_S = 600        # baseline = median of skin readings from 10 min ago ...
SKIN_BASE_OLDEST_S = 6 * 3600   # ... back to 6 h ago
SKIN_BASE_MIN_N = 10            # readings needed before a baseline is shown
SKIN_CHANGE_FLAG_C = 1.0        # highlight only; there is no validated threshold, so it never alerts
ESCALATE_AFTER_S = 120          # default: carer view after an alert goes unacknowledged this long
# Typical clinically meaningful 6 h change per vital, used only to RANK trends for the SBAR summary.
TREND_SCALE = {"HR": 20.0, "O2Sat": 3.0, "Temp": 1.0, "Resp": 5.0}
TREND_NAME = {"HR": ("Heart rate", "bpm"), "O2Sat": ("SpO2", "%"), "Temp": ("Temperature", "°C"),
              "Resp": ("Respiratory rate", "/min")}
SPO2_FRESH_S = 600      # SpO2 is a spot reading; keep it 10 minutes
RR_STABLE_N = 2         # respiratory rate counts after this many agreeing readings (2 s apart)
RR_STABLE_SPREAD = 4.0  # ... that all lie within this many breaths/min of each other
RR_EVERY_S = 2          # re-estimate respiratory rate every 2 s
RR_FAIL_CLEAR = 3       # consecutive misses before clearing the settling history
RR_FRESH_S = 30
OVERRIDE_TTL_S = 600
ALERT_SCORE = 5         # NEWS2 "urgent response" threshold
ALERT_TICKS = 2         # consecutive 1 s ticks above threshold before alerting
ACK_MUTE_S = 300

WATCH_REQUIRED = {"t", "hr", "spo2", "skin_temp_c", "source"}
WATCH_ALLOWED = WATCH_REQUIRED | {"spo2_t", "ambient_c", "ibi_ms"}   # ambient_c, ibi_ms: context only

accel = deque(maxlen=int(60 * FS))  # (x, y, z) in g, last 60 s (RR uses the last 30 s; /api/imu/raw serves all)
state = {
    "watch": {"t": None, "hr": None, "spo2": None, "spo2_t": None, "skin_temp_c": None, "skin_t": None,
              "rx": None, "count": 0},
    "rr_hist": deque(maxlen=3),
    "rr_misses": 0,
    "rr_last_eval": 0.0,
    "skin_hist": deque(maxlen=1500),    # (epoch s, skin C): about a reading a minute, ~24 h
    "escalate_after_s": ESCALATE_AFTER_S,
    "override": {},     # name -> {"v": float, "until": epoch s}
    "rr": {"rr": None, "reason": "starting", "at": None},
    "env": {"temp_c": None, "hum_pct": None, "lux": None, "ir": None},
    "devices": "",
    "imu_hz": None,
    "alert": {"active": False, "streak": 0, "muted_until": 0, "last_buzz": 0, "since": None},
    "vibe_request": None,
    "model": {"risk": None, "note": "model not loaded"},
    "model_at": None,                              # when the live model last scored
    "still": {"motion_g": None, "still": False},   # chest IMU resting detector
    "rigor": {"shaking": False, "shake_g": None, "ratio": None, "since": None, "reason": "warming up"},
    "profile": pathways.load_profile(),            # pathway profile (general/post_surgery/chemo/care_home)
    "last_triggers": [],                           # triggers from the most recent check-in
}

faults = Faults()                              # demo fault fixtures (liveness.py)
net_check = NetCheck()                         # internet / LAN reachability, every 30 s
baseline = Baseline(pathlib.Path(__file__).parent / "baseline.json")   # personal resting HR / HRV baseline
handoff = handoff_mod.Handoff()                # owned nurse handoff queue + tamper-evident audit log


def validate_watch(body):
    if not isinstance(body, dict):
        return ["body is not a JSON object"]
    errs = []
    keys = set(body)
    if not WATCH_REQUIRED <= keys <= WATCH_ALLOWED:
        errs.append(f"keys {sorted(keys)} must include {sorted(WATCH_REQUIRED)} and may add {sorted(WATCH_ALLOWED - WATCH_REQUIRED)}")
        return errs
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not (isinstance(body["t"], int) and not isinstance(body["t"], bool)):
        errs.append("t must be an integer (epoch ms)")
    for k in ("hr", "spo2", "skin_temp_c", "spo2_t", "ambient_c"):
        if k in body and body[k] is not None and not num(body[k]):
            errs.append(f"{k} must be a number or null")
    ibi = body.get("ibi_ms")
    if ibi is not None and not (isinstance(ibi, list) and all(num(v) for v in ibi)):
        errs.append("ibi_ms must be a list of numbers or null")
    if body["source"] != "watch":
        errs.append('source must be "watch"')
    return errs


def accept_watch(body):
    w = state["watch"]
    if w["t"] is not None and body["t"] < w["t"]:
        return  # a buffered, older sample: the newer one stays
    w.update(t=body["t"], hr=body["hr"], rx=time.time())
    if body["skin_temp_c"] is not None:   # the watch sends null between its once-a-minute readings: keep the last one
        sh = state["skin_hist"]   # the watch repeats a reading for a few minutes: store a new point only on change or per minute
        if not sh or body["skin_temp_c"] != sh[-1][1] or body["t"] / 1000 - sh[-1][0] >= 60:
            sh.append((body["t"] / 1000, body["skin_temp_c"]))
        w["skin_temp_c"] = body["skin_temp_c"]
        w["skin_t"] = body["t"]
    if body["spo2"] is not None:
        w["spo2"] = body["spo2"]
        w["spo2_t"] = body.get("spo2_t") or body["t"]
    if body.get("ambient_c") is not None:
        w["ambient_c"] = body["ambient_c"]
        w["ambient_t"] = body["t"]   # so the dashboard can drop it when the watch stops sending it
    # Heart-rate variability (context only, not scored): RMSSD over the last ~5 min of plausible intervals.
    ibis = state.setdefault("ibi_hist", deque(maxlen=400))
    for v in body.get("ibi_ms") or []:
        if 300 <= v <= 2000:
            ibis.append((body["t"] / 1000, float(v)))
    recent = [v for t, v in ibis if body["t"] / 1000 - t <= 300]
    if len(recent) >= 30:
        d = [b - a for a, b in zip(recent, recent[1:]) if abs(b - a) < 200]   # drop ectopic/artefact jumps
        w["rmssd_ms"] = round((sum(x * x for x in d) / len(d)) ** 0.5, 1) if d else None
        w["rmssd_t"] = body["t"]
    w["count"] += 1


def effective_vitals(now):
    """One record of the best current value per vital, with where each came from."""
    out = {}
    w = state["watch"]
    age = (now - w["t"] / 1000) if w["t"] else None
    rr = state["rr"]

    candidates = {
        "hr": (w["hr"] if age is not None and age <= HR_FRESH_S else None, "watch"),
        "spo2": (w["spo2"] if w["spo2_t"] and now - w["spo2_t"] / 1000 <= SPO2_FRESH_S else None, "watch"),
        "temp": (None, "watch"),   # core temperature: only a manual override can supply it; the watch gives skin (below)
        "rr": (rr["rr"] if rr["rr"] is not None and rr["at"] and now - rr["at"] <= RR_FRESH_S else None, "imu"),
    }
    for name, (value, source) in candidates.items():
        ov = state["override"].get(name)
        if ov and ov["until"] > now:
            out[name] = {"v": ov["v"], "src": "override"}
        elif value is not None:
            out[name] = {"v": round(value, 2) if name == "temp" else value, "src": source}
        else:
            out[name] = {"v": None, "src": None}
    # Skin temperature against the wearer's own baseline (median of readings 10 min to 6 h ago).
    base = [v for t, v in state["skin_hist"] if now - SKIN_BASE_OLDEST_S <= t <= now - SKIN_BASE_NEWEST_S]
    skin = {"v": None, "src": None, "baseline": None, "delta": None, "n_base": len(base),
            "need": SKIN_BASE_MIN_N, "flag_c": SKIN_CHANGE_FLAG_C}
    if w["skin_t"] and now - w["skin_t"] / 1000 <= TEMP_FRESH_S:
        skin.update(v=round(w["skin_temp_c"], 2), src="watch")
        if len(base) >= SKIN_BASE_MIN_N:
            b = sorted(base)[len(base) // 2]
            skin.update(baseline=round(b, 2), delta=round(w["skin_temp_c"] - b, 2))
    out["skin"] = skin
    return out


try:
    _risk_model = RiskModel()
    state["model"] = {"risk": None, "note": "collecting hourly history (0/8 h)", "alert": False,
                      "engine": _risk_model.name, "hours": 0, "trend": {}}
    print(f"risk model loaded: engine={_risk_model.name} threshold={_risk_model.threshold}", flush=True)
except Exception as e:   # the dashboard must still come up without the model
    _risk_model = None
    state["model"] = {"risk": None, "note": f"model failed to load: {e}"}
    print("risk model FAILED:", e, flush=True)


class _LockedModel:
    """Live scoring, replay and stress lab all call the model; the .eim process handles one request at a time."""

    def __init__(self, rm):
        self._rm = rm
        self.name = rm.name
        self.threshold = rm.threshold

    def score(self, hourly):
        with MODEL_LOCK:
            return self._rm.score(hourly)


hourly = HourlyVitals()
_locked_model = _LockedModel(_risk_model) if _risk_model else None
replay = Replay(_locked_model) if _locked_model else None
REPLAY_LOCK = threading.Lock()   # Replay.state() scores new hours and mutates its timeline
STRESS_LOCK = threading.Lock()   # serialize stress.run() cache/scoring calls


# Held-out test results from docs/results.md (main thread, Edge Impulse BYOM LightGBM vs 4-vital NEWS2 rule).
RESULTS_NOTE = ("Held-out patients, cutoff 0.55 chosen on validation: model score flags 78% of sepsis patients "
                "in the 24 h before onset with 0.91 separate false alerts per patient-day; the 4-vital NEWS2 rule flags 76% "
                "with 1.61. The model's alerts last longer (22% vs 16% of hours), so at equal alarm time NEWS2 catches more; "
                "the device shows both.")


def replay_state():
    if replay is None:
        return {"active": False, "cases": [], "note": "model not loaded"}
    with REPLAY_LOCK:
        return replay.state()


def risk_from_model(vitals, now=None):
    """Feed the current vitals into the hourly history and score it.

    The model works on hourly trends, so a live patient needs 8 h of history before it
    answers (the note says how many hours are collected). Returns the dict stored in
    state["model"]: risk (0-100 or None), note, alert, engine, hours, threshold, trend.
    """
    if _risk_model is None:
        return state["model"]
    now = time.time() if now is None else now
    hourly.add(now, hr=vitals["hr"]["v"], spo2=vitals["spo2"]["v"],
               temp=vitals["temp"]["v"], rr=vitals["rr"]["v"])
    with MODEL_LOCK:
        return _risk_model.score(hourly.history())


def snapshot():
    now = time.time()
    with LOCK:
        v = effective_vitals(now)
        n2 = news2(rr=v["rr"]["v"], spo2=v["spo2"]["v"], temp=v["temp"]["v"], hr=v["hr"]["v"])
        w = state["watch"]
        # Age of every live reading, so the dashboard can grey out stale ones (override values have no age).
        rr_state = state["rr"]
        ages = {"hr": age_info(now - w["t"] / 1000 if w["t"] else None, "hr"),
                "rr": age_info(now - rr_state["at"] if rr_state.get("at") else None, "rr"),
                "spo2": age_info(now - w["spo2_t"] / 1000 if w["spo2_t"] else None, "spo2"),
                "skin": age_info(now - w["skin_t"] / 1000 if w["skin_t"] else None, "skin")}
        for k in ("hr", "rr", "spo2"):
            if v[k]["src"] in ("watch", "imu"):
                v[k].update(ages[k])
        if v["skin"]["v"] is not None:
            v["skin"].update(ages["skin"])
        counts = {"fresh": 0, "stale": 0, "missing": 0}
        for k in ("hr", "rr", "spo2", "skin"):
            if v[k]["v"] is None:
                counts["missing"] += 1
            elif v[k].get("stale"):
                counts["stale"] += 1
            else:
                counts["fresh"] += 1
        w_age = now - w["rx"] if w["rx"] else None
        engine_age = now - state["model_at"] if state["model_at"] else None
        return {
            "now": now,
            "links": {
                "watch": {"state": "never" if w_age is None else "connected" if w_age <= WATCH_OK_S
                          else "slow" if w_age <= WATCH_LOST_S else "disconnected",
                          "last_age_s": round(w_age, 1) if w_age is not None else None},
                "readings": {**counts, "of": 4},
                "engine": {"name": state["model"].get("engine") or "none",
                           "state": "starting" if engine_age is None else "running" if engine_age <= ENGINE_OK_S else "stalled",
                           "last_scored_age_s": round(engine_age, 1) if engine_age is not None else None},
                "net": net_check.status(now, simulated_cut=faults.active("internet_cut")),
                "faults": faults.status(),
            },
            "rest": dict(state["still"]),
            "baseline": baseline.summary(now, state["still"]["still"]),   # context only, never scored
            "vitals": v,
            "news2": n2,
            "risk": state["model"],
            "alert": {k: state["alert"][k] for k in ("active", "streak")}
            | {"muted": state["alert"]["muted_until"] > now},
            "rr_detail": state["rr"],
            "rigor": state["rigor"],
            "env": state["env"],
            "devices": state["devices"],
            "imu_hz": state["imu_hz"],
            "watch": {"packets": w["count"], "last_age_s": round(now - w["rx"], 1) if w["rx"] else None},
            # context only, never scored; dropped when the watch has stopped sending it
            "context": {
                "ambient_c": w.get("ambient_c") if w.get("ambient_t") and now - w["ambient_t"] / 1000 <= 180 else None,
                "rmssd_ms": w.get("rmssd_ms") if w.get("rmssd_t") and now - w["rmssd_t"] / 1000 <= 300 else None,
            },
        }


RED_FLAGS = ("Call 999 now if the person is confused or has slurred speech, is struggling to breathe, has blue, "
             "pale or mottled skin, is very sleepy or hard to wake, has passed no urine all day, has extreme "
             "shivering or muscle pain, or says they feel they are going to die. Call 111 if the alert keeps "
             "going and they seem unwell, or you are not sure what to do.")


def build_escalation(snap, rs, now, force=False):
    """Carer view: shown when an alert has gone unacknowledged for `escalate_after_s`.

    SBAR = Situation, Background, Assessment, Recommendation. The 3 vitals with the largest 6 h change
    come from the model's own trend output (ranked by change relative to TREND_SCALE).
    """
    with LOCK:
        al = state["alert"]
        since, muted, active = al["since"], al["muted_until"] > now, al["active"]
        after = state["escalate_after_s"]
    out = {"active": False, "after_s": after, "alert_age_s": round(now - since) if (active and since) else None}
    if not force and not (active and since and not muted and now - since >= after):
        return out
    rep = bool(rs.get("active"))
    model = rs["risk"] if rep else snap["risk"]
    n2 = rs["news2"] if rep else snap["news2"]
    if rep:
        vit = rs["vitals"]
    else:
        vit = {k: snap["vitals"][k]["v"] for k in ("hr", "spo2", "temp", "rr")}
        vit["skin"] = snap["vitals"]["skin"]["v"]

    ranked = sorted(((abs(v) / TREND_SCALE.get(k, 1.0), k, v) for k, v in (model.get("trend") or {}).items()),
                    reverse=True)[:3]
    trend_lines = []
    for _, k, v in ranked:
        name, unit = TREND_NAME.get(k, (k, ""))
        trend_lines.append(f"{name} {v:+.1f} {unit} over the last 6 h")
    if not trend_lines:
        trend_lines.append("6 h trends not available yet (the model needs 8 h of history)")

    shown = lambda x, d=0: "not measured" if x is None else f"{x:.{d}f}"
    now_line = (f"Now: heart rate {shown(vit['hr'])} bpm, SpO2 {shown(vit['spo2'])}%, "
                f"respiratory rate {shown(vit['rr'])}/min, " +
                (f"temperature {shown(vit['temp'], 1)} °C (core)." if rep or vit["temp"] is not None
                 else f"wrist skin temperature {shown(vit.get('skin'), 1)} °C (not core)."))
    parts = ", ".join(f"{k} {p}" for k, p in n2["parts"].items()) or "no scorable vitals"
    news_line = (f"NEWS2 {n2['score']} ({parts}; blood pressure, consciousness and oxygen use are not measured)"
                 + (f"; not scored: {', '.join(n2['missing'])}" if n2["missing"] else "."))

    risk = model.get("risk")
    thr = model.get("threshold")
    situation = (("REPLAY OF A RECORDED ICU CASE, not a live patient. " if rep else "") +
                 f"Automated early-warning alert, not acknowledged for {out['alert_age_s']} s. " +
                 (f"Model sepsis risk {risk:.0f}% (alert threshold {thr:.0f}%). " if risk is not None and thr is not None else "") +
                 f"NEWS2 {n2['score']}.")
    out.update(active=True, replay=rep, sbar={
        "situation": situation,
        "background": ("Wearable monitoring prototype (smartwatch plus chest sensor). The device has no record of the "
                       "person's history, medicines or infection source."),
        "assessment": trend_lines + [now_line, news_line],
        "recommendation": "Check on the person now and take a full set of observations. " + RED_FLAGS,
        "disclaimer": "Draft wording for a decision-support prototype; a clinician should confirm it before real use.",
    })
    return out


rigor_det = RigorDetector()
pat_session = pat_mod.PatSession()
PAT_LOCK = threading.Lock()


def pat_demo():
    """Replay a recorded 28 s ECG + PPG check (a fallback for the stage when no watch is wired up)."""
    fx = json.loads((HERE / "model" / "ecg_sample.json").read_text())
    with PAT_LOCK:
        pat_session.reset()
    n = len(fx["pt"])
    for a in range(0, n, 50):
        b = min(n, a + 50)
        with PAT_LOCK:
            pat_session.add_chunk({"pt": fx["pt"][a:b], "ecg": fx["ecg"][10 * a:10 * b],
                                   "ppg": fx["ppg"][2 * a:2 * b], "lead": fx["lead"][a:b]})
        time.sleep(1.0)


def tick():
    """Once a second: read the STM32, update RR, evaluate the alert."""
    now = time.time()
    try:
        raw = Bridge.call("drain")
        head, _, body = raw.partition("|")
        t0, _, t1 = head.partition(",")
        samples = [s.split(",") for s in body.split(";") if s]
        frozen = faults.active("imu_freeze")   # demo fixture: pretend the chest sensor stopped
        with LOCK:
            for s in ([] if frozen else samples):
                if len(s) == 3:
                    accel.append((int(s[0]) / 1000, int(s[1]) / 1000, int(s[2]) / 1000))
            state["imu_hz"] = 0 if frozen else len(samples)
    except Exception as e:  # keep the loop alive if the STM32 is busy
        print("drain failed:", e, flush=True)

    if int(now) % 2 == 0:
        try:
            temp, hum, lux, ir = Bridge.call("env").split(",")
            fl = lambda x: None if x == "nan" else float(x)
            with LOCK:
                state["env"] = {"temp_c": fl(temp), "hum_pct": fl(hum),
                                "lux": None if int(lux) < 0 else int(lux),
                                "ir": None if int(ir) < 0 else int(ir)}
                state["devices"] = Bridge.call("status")
        except Exception as e:
            print("env failed:", e, flush=True)

    # Resting detector and personal baseline (context only, never scored).
    with LOCK:
        mx, my, mz = ([a[i] for a in accel] for i in range(3))
    m = motion_level(mx, my, mz)
    still = m is not None and m < REST_MOTION_G and not faults.active("imu_freeze")
    with LOCK:
        w = state["watch"]
        hr_now = w["hr"] if w["t"] and now - w["t"] / 1000 <= HR_FRESH_S else None
        hrv_now = w.get("rmssd_ms") if w.get("rmssd_t") and now - w["rmssd_t"] / 1000 <= 300 else None
        state["still"] = {"motion_g": None if m is None else round(m, 4), "still": still}
        baseline.add(now, still, hr_now, hrv_now)
        shake_in = None if faults.active("imu_freeze") else (mx[-100:], my[-100:], mz[-100:])
    # Shaking-chill detector: context for a person to confirm, never scored.
    if shake_in is not None:
        state["rigor"] = rigor_det.update(now, *shake_in)
    else:
        state["rigor"] = {**state["rigor"], "shaking": False, "reason": "chest sensor stopped"}

    if now - state["rr_last_eval"] >= RR_EVERY_S:
        state["rr_last_eval"] = now
        if faults.active("imu_freeze"):
            est = {"rr": None, "reason": "chest sensor stopped", "motion_g": None, "amplitude_g": None, "strength": None}
        else:
            with LOCK:
                xs, ys, zs = ([a[i] for a in accel] for i in range(3))
            est = estimate_rr(xs, ys, zs)
        with LOCK:
            hist = state["rr_hist"]
            if est["rr"] is None:
                state["rr_misses"] += 1
                if state["rr_misses"] >= RR_FAIL_CLEAR:
                    hist.clear()
            else:
                state["rr_misses"] = 0
                hist.append(est["rr"])
            recent = list(hist)[-RR_STABLE_N:]
            stable = len(recent) >= RR_STABLE_N and max(recent) - min(recent) <= RR_STABLE_SPREAD
            if est["rr"] is not None and not stable:
                est = {**est, "rr": None, "reason": f"settling ({len(recent)}/{RR_STABLE_N})"}
            elif stable and est["rr"] is not None:
                est = {**est, "rr": round(sorted(hist)[len(hist) // 2], 1)}
            prev = state["rr"]
            if est["rr"] is not None:
                state["rr"] = {**est, "at": now}
            elif prev.get("rr") is not None and prev.get("at") and now - prev["at"] <= RR_FRESH_S:
                # Hold the last good reading during brief movement/glitches; age_info marks it stale after STALE_S["rr"].
                state["rr"] = {**est, "rr": prev["rr"], "at": prev["at"]}
            else:
                state["rr"] = {**est, "at": prev.get("at")}

    snap = snapshot()
    if int(now) % MODEL_EVERY_S == 0:
        try:
            res = risk_from_model(snap["vitals"], now)
            with LOCK:
                state["model"] = res
                state["model_at"] = now
            snap["risk"] = res
        except Exception as e:
            print("model failed:", e, flush=True)

    rs = replay_state()
    with LOCK:
        al = state["alert"]
        if rs.get("active"):
            cond = bool(rs["risk"]["alert"])   # a replay drives the alert from its own recorded patient
        else:
            cond = (snap["news2"]["score"] >= ALERT_SCORE or snap["news2"]["any_red"]
                    or bool(snap["risk"].get("alert")))
        if cond:
            al["streak"] += 1
        else:
            al["streak"] = 0
            al["muted_until"] = 0
        was_active = al["active"]
        al["active"] = al["streak"] >= ALERT_TICKS
        opened_alert = al["active"] and not was_active
        if opened_alert:
            al["since"] = now        # the escalation clock starts when the alert first goes active
        elif not al["active"]:
            al["since"] = None
            al["task_id"] = None
        buzz = al["active"] and al["muted_until"] <= now and now - al["last_buzz"] >= 5
        req = state["vibe_request"]
        state["vibe_request"] = None
        if buzz:
            al["last_buzz"] = now
    if opened_alert:
        try:
            rep = bool(rs.get("active"))
            src = "model" if (rs["risk"]["alert"] if rep else snap["risk"].get("alert")) else "news2"
            esc_sbar = build_escalation(snap, rs, now, force=True).get("sbar") or {}
            task = handoff.open_task(src, "alert", esc_sbar, handoff_mod.compact_snapshot(snap, rs),
                                     replay=rep, priority="urgent", now=now)
            with LOCK:
                al["task_id"] = task["id"]
                acknowledged_at = al["muted_until"] - ACK_MUTE_S
            if acknowledged_at >= now:
                handoff.wearer_ack(task["id"], now=acknowledged_at)
        except Exception as e:
            print("handoff open_task failed:", e, flush=True)
    if buzz and req is None:
        req = (500, 45)
    if req:
        try:
            Bridge.call("vibe", req[0], req[1])
        except Exception as e:
            print("vibe failed:", e, flush=True)


def audit_status():
    n_head, head = handoff.audit_head()
    ok, n_rows = handoff.verify_audit()
    return {"ok": ok, "n_rows": n_rows, "head": head if n_head == n_rows else None}


# Shared stylesheet and helpers for the three pages; the only static files the board serves.
ASSETS = {"/ui.css": ("ui.css", "text/css; charset=utf-8"),
          "/ui.js": ("ui.js", "text/javascript; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _page(self, filename, kind="text/html; charset=utf-8"):
        data = (HERE / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._page("dashboard.html")
        elif self.path.split("?")[0] in ASSETS:
            self._page(*ASSETS[self.path.split("?")[0]])
        elif self.path in ("/pat", "/pat.html"):
            self._page("pat.html")
        elif self.path == "/api/pat":
            with PAT_LOCK:
                self._json(200, pat_session.analyse())
        elif self.path == "/api/state":
            snap = snapshot()
            rs = replay_state()
            snap["escalation"] = build_escalation(snap, rs, snap["now"])
            snap["handoff_receipt"] = handoff.wearer_receipt(replay=rs.get("active", False))
            self._json(200, snap)
        elif self.path == "/api/replay":
            rs = replay_state()
            if replay is not None and rs.get("active"):
                rs = {**rs, "cases": replay.cases(), "results": RESULTS_NOTE}
            else:
                rs = {**rs, "results": RESULTS_NOTE}
            self._json(200, rs)
        elif self.path in ("/stress", "/stress.html"):
            self._page("stress.html")
        elif self.path in ("/handoff", "/handoff.html"):
            self._page("handoff.html")
        elif self.path == "/api/handoff" or self.path.startswith("/api/handoff?"):
            query = parse_qs(urlparse(self.path).query)
            self._json(200, {"tasks": handoff.list(active_only=query.get("all") != ["1"]),
                             "audit": audit_status()})
        elif self.path == "/api/audit":
            self._json(200, audit_status())
        elif self.path.startswith("/api/fhir/"):
            _, _, _, task_id, *suffix = self.path.split("/")
            task = handoff.get(task_id)
            if task is None or suffix not in ([], ["qr"]):
                return self._json(404, {"ok": False, "error": "unknown FHIR task or route"})
            bundle = fhir.bundle(task)
            if suffix == ["qr"]:
                host, port = self.server.server_address
                payload = fhir.qr_payload(bundle, host=None if host == "0.0.0.0" else host, port=port)
                return self._json(200, {"payload": payload, "inline": payload.startswith(fhir.PREFIX),
                                        "chars": len(payload)})
            self._json(200, bundle)
        elif self.path == "/api/stress/summary":
            code, payload = stress.api_summary()
            self._json(code, payload)
        elif self.path == "/api/stress" or self.path.startswith("/api/stress?"):
            if _locked_model is None:
                return self._json(503, {"ok": False, "error": "model not loaded"})
            with STRESS_LOCK:
                code, payload = stress.api_stress(parse_qs(urlparse(self.path).query), _locked_model)
            self._json(code, payload)
        elif self.path.startswith("/api/imu/raw"):
            q = parse_qs(urlparse(self.path).query)
            try:
                secs = max(1.0, min(60.0, float(q.get("seconds", ["10"])[0])))
            except ValueError:
                return self._json(400, {"ok": False, "errors": ["seconds must be a number"]})
            with LOCK:
                samples = list(accel)[-int(secs * FS):]
            self._json(200, {"fs": FS, "units": "g", "n": len(samples), "samples": samples,
                             "end_time": time.time()})
        else:
            self.send_error(404)

    def do_POST(self):
        body = self._body()
        # Use the routes named in handoff.html and pathways.validate_checkin().
        if self.path.startswith("/api/handoff/"):
            _, _, _, task_id, *suffix = self.path.split("/")
            if suffix not in (["accept"], ["resolve"]):
                return self._json(404, {"ok": False, "error": "unknown handoff route"})
            if not isinstance(body, dict):
                return self._json(400, {"ok": False, "error": "body must be a JSON object"})
            try:
                if suffix == ["accept"]:
                    task = handoff.accept(task_id, body.get("nurse"))
                else:
                    task = handoff.resolve(task_id, body.get("action"), body.get("outcome"))
            except handoff_mod.HandoffError as exc:
                return self._json(exc.code, {"ok": False, "error": str(exc)})
            return self._json(200, {"ok": True, "task": task})
        if self.path == "/api/ecg":
            chunk, errors = pat_mod.validate_chunk(body)
            if errors:
                return self._json(400, {"ok": False, "errors": errors})
            with PAT_LOCK:
                pat_session.add_chunk(chunk)
            return self._json(200, {"ok": True})
        if self.path == "/api/pat/reset":
            with PAT_LOCK:
                pat_session.reset()
            return self._json(200, {"ok": True})
        if self.path == "/api/pat/demo":
            threading.Thread(target=pat_demo, daemon=True).start()
            return self._json(200, {"ok": True})
        if self.path == "/api/checkin":
            signs = body.get("soft_signs") if isinstance(body, dict) else None
            if isinstance(signs, list) and any(not isinstance(sign, str) for sign in signs):
                return self._json(400, {"ok": False, "errors": ["soft_signs must contain strings"]})
            manual, errors = pathways.validate_checkin(body)
            if errors:
                return self._json(400, {"ok": False, "errors": errors})
            rs, snap = replay_state(), snapshot()
            with LOCK:
                profile = state["profile"]
            compact = handoff_mod.compact_snapshot(snap, rs, manual)
            triggers = pathways.evaluate(profile, compact["vitals"], manual, now=snap["now"])
            tasks = [handoff.open_task(
                trigger["task_source"], trigger["rule"], pathways.sbar(trigger, profile, manual),
                compact, replay=bool(rs.get("active")), priority=trigger["severity"], now=snap["now"],
            ) for trigger in triggers]
            with LOCK:
                state["last_triggers"] = triggers
            return self._json(200, {"ok": True, "triggers": triggers, "tasks": tasks})
        if self.path == "/fault" and isinstance(body, dict):
            try:
                if body.get("clear"):
                    faults.clear(body.get("kind"))
                else:
                    faults.set(body.get("kind"), body.get("seconds", 60))
            except (ValueError, TypeError) as e:
                return self._json(400, {"ok": False, "errors": [str(e)]})
            return self._json(200, {"ok": True, "faults": faults.status()})
        if self.path == "/vitals":
            if faults.active("watch_drop"):   # demo fixture: refuse like a dead link, so the watch buffers and retries
                return self._json(503, {"ok": False, "errors": ["simulated outage: watch link down"]})
            errs = validate_watch(body) if body is not None else ["invalid JSON"]
            if errs:
                print("REJECTED /vitals:", errs, flush=True)
                return self._json(400, {"ok": False, "errors": errs})
            with LOCK:
                accept_watch(body)
            return self._json(200, {"ok": True})
        if self.path == "/override" and isinstance(body, dict):
            until = time.time() + OVERRIDE_TTL_S
            with LOCK:
                for name in ("hr", "spo2", "temp", "rr"):
                    if name in body:
                        if body[name] is None:
                            state["override"].pop(name, None)
                        else:
                            state["override"][name] = {"v": float(body[name]), "until": until}
            return self._json(200, {"ok": True})
        if self.path == "/replay/start":
            if replay is None or not isinstance(body, dict):
                return self._json(400, {"ok": False, "errors": ["replay unavailable (model not loaded) or bad body"]})
            case = body.get("case")
            if case not in replay.by_id:
                return self._json(400, {"ok": False, "errors": [f"unknown case; choose from {sorted(replay.by_id)}"]})
            try:
                sph = max(0.2, min(30.0, float(body.get("seconds_per_hour", 1.5))))
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "errors": ["seconds_per_hour must be a number"]})
            with REPLAY_LOCK:
                handoff.cancel_open(replay=True, reason="Replay changed")
                replay.start(case, seconds_per_hour=sph)
            return self._json(200, {"ok": True})
        if self.path == "/replay/stop":
            if replay is not None:
                with REPLAY_LOCK:
                    replay.stop()
                    handoff.cancel_open(replay=True, reason="Replay stopped")
            return self._json(200, {"ok": True})
        if self.path == "/vibe":
            with LOCK:
                state["vibe_request"] = (400, 45)
            return self._json(200, {"ok": True})
        if self.path == "/escalation" and isinstance(body, dict):
            try:
                secs = max(5.0, min(3600.0, float(body.get("seconds", ESCALATE_AFTER_S))))
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "errors": ["seconds must be a number (5 to 3600)"]})
            with LOCK:
                state["escalate_after_s"] = secs
            return self._json(200, {"ok": True, "after_s": secs})
        if self.path == "/ack":
            now = time.time()
            with LOCK:
                state["alert"]["muted_until"] = now + ACK_MUTE_S
                task_id = state["alert"].get("task_id")
            task = handoff.wearer_ack(task_id, now=now) if task_id else None
            return self._json(200, {"ok": True, "task": task})
        self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"dashboard + /vitals on port {server.server_port}", flush=True)
    server.serve_forever()


threading.Thread(target=serve, daemon=True).start()


def loop():
    try:
        tick()
    except Exception as e:
        print("tick failed:", e, flush=True)
    time.sleep(1)


App.run(user_loop=loop)
