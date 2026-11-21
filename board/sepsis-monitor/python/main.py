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

from model_runner import HourlyVitals, RiskModel
from news2 import news2
from replay import Replay
from resp import FS, estimate_rr

HERE = pathlib.Path(__file__).parent
PORT = 8000
LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()   # the .eim runner is one process: one scoring call at a time
MODEL_EVERY_S = 5               # live model re-score interval

HR_FRESH_S = 30         # watch hr older than this is treated as missing
TEMP_FRESH_S = 180      # watch reads skin temp about once a minute; hold the last good one for 3 minutes
SKIN_TO_CORE_C = 3.5    # rough estimate: skin runs ~2-4 C below core. NEWS2 bands are for core temperature.
SPO2_FRESH_S = 600      # SpO2 is a spot reading; keep it 10 minutes
RR_STABLE_N = 3         # respiratory rate counts only after this many agreeing readings (5 s apart)
RR_STABLE_SPREAD = 3.0  # ... that all lie within this many breaths/min of each other
RR_FRESH_S = 20
OVERRIDE_TTL_S = 600
ALERT_SCORE = 5         # NEWS2 "urgent response" threshold
ALERT_TICKS = 2         # consecutive 1 s ticks above threshold before alerting
ACK_MUTE_S = 300

WATCH_REQUIRED = {"t", "hr", "spo2", "skin_temp_c", "source"}
WATCH_ALLOWED = WATCH_REQUIRED | {"spo2_t"}

accel = deque(maxlen=int(60 * FS))  # (x, y, z) in g, last 60 s (RR uses the last 30 s; /api/imu/raw serves all)
state = {
    "watch": {"t": None, "hr": None, "spo2": None, "spo2_t": None, "skin_temp_c": None, "skin_t": None,
              "rx": None, "count": 0},
    "rr_hist": deque(maxlen=RR_STABLE_N),
    "override": {},     # name -> {"v": float, "until": epoch s}
    "rr": {"rr": None, "reason": "starting", "at": None},
    "env": {"temp_c": None, "hum_pct": None, "lux": None, "ir": None},
    "devices": "",
    "imu_hz": None,
    "alert": {"active": False, "streak": 0, "muted_until": 0, "last_buzz": 0},
    "vibe_request": None,
    "model": {"risk": None, "note": "model not loaded"},
}


def validate_watch(body):
    if not isinstance(body, dict):
        return ["body is not a JSON object"]
    errs = []
    keys = set(body)
    if not WATCH_REQUIRED <= keys <= WATCH_ALLOWED:
        errs.append(f"keys {sorted(keys)} must include {sorted(WATCH_REQUIRED)} and may add spo2_t")
        return errs
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not (isinstance(body["t"], int) and not isinstance(body["t"], bool)):
        errs.append("t must be an integer (epoch ms)")
    for k in ("hr", "spo2", "skin_temp_c", "spo2_t"):
        if k in body and body[k] is not None and not num(body[k]):
            errs.append(f"{k} must be a number or null")
    if body["source"] != "watch":
        errs.append('source must be "watch"')
    return errs


def accept_watch(body):
    w = state["watch"]
    if w["t"] is not None and body["t"] < w["t"]:
        return  # a buffered, older sample: the newer one stays
    w.update(t=body["t"], hr=body["hr"], rx=time.time())
    if body["skin_temp_c"] is not None:   # the watch sends null between its once-a-minute readings: keep the last one
        w["skin_temp_c"] = body["skin_temp_c"]
        w["skin_t"] = body["t"]
    if body["spo2"] is not None:
        w["spo2"] = body["spo2"]
        w["spo2_t"] = body.get("spo2_t") or body["t"]
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
        "temp": (w["skin_temp_c"] + SKIN_TO_CORE_C
                 if w["skin_t"] and now - w["skin_t"] / 1000 <= TEMP_FRESH_S else None, "watch"),
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
    if out["temp"]["src"] == "watch":
        out["temp"]["skin_c"] = w["skin_temp_c"]   # extra key: the raw skin reading behind the core estimate
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
    """Live scoring and replay both call the model; the .eim process handles one request at a time."""

    def __init__(self, rm):
        self._rm = rm

    def score(self, hourly):
        with MODEL_LOCK:
            return self._rm.score(hourly)


hourly = HourlyVitals()
replay = Replay(_LockedModel(_risk_model)) if _risk_model else None
REPLAY_LOCK = threading.Lock()   # Replay.state() scores new hours and mutates its timeline


# Held-out test results from docs/results.md (main thread, Edge Impulse BYOM LightGBM vs 4-vital NEWS2 rule).
RESULTS_NOTE = ("Held-out patients: model flags 74% of sepsis patients in the 24 h before onset with "
                "0.82 false alerts per patient-day; the 4-vital NEWS2 rule flags 75% with 1.60.")


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
        return {
            "now": now,
            "vitals": v,
            "news2": n2,
            "risk": state["model"],
            "alert": {k: state["alert"][k] for k in ("active", "streak")}
            | {"muted": state["alert"]["muted_until"] > now},
            "rr_detail": state["rr"],
            "env": state["env"],
            "devices": state["devices"],
            "imu_hz": state["imu_hz"],
            "watch": {"packets": w["count"], "last_age_s": round(now - w["rx"], 1) if w["rx"] else None},
        }


def tick():
    """Once a second: read the STM32, update RR, evaluate the alert."""
    now = time.time()
    try:
        raw = Bridge.call("drain")
        head, _, body = raw.partition("|")
        t0, _, t1 = head.partition(",")
        samples = [s.split(",") for s in body.split(";") if s]
        with LOCK:
            for s in samples:
                if len(s) == 3:
                    accel.append((int(s[0]) / 1000, int(s[1]) / 1000, int(s[2]) / 1000))
            state["imu_hz"] = len(samples)
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

    if int(now) % 5 == 0:
        with LOCK:
            xs, ys, zs = ([a[i] for a in accel] for i in range(3))
        est = estimate_rr(xs, ys, zs)
        with LOCK:
            hist = state["rr_hist"]
            if est["rr"] is None:
                hist.clear()
            else:
                hist.append(est["rr"])
            stable = len(hist) == RR_STABLE_N and max(hist) - min(hist) <= RR_STABLE_SPREAD
            if est["rr"] is not None and not stable:
                est = {**est, "rr": None, "reason": f"settling ({len(hist)}/{RR_STABLE_N})"}
            elif stable:
                est = {**est, "rr": round(sorted(hist)[len(hist) // 2], 1)}
            state["rr"] = {**est, "at": now if est["rr"] is not None else state["rr"].get("at")}

    snap = snapshot()
    if int(now) % MODEL_EVERY_S == 0:
        try:
            res = risk_from_model(snap["vitals"], now)
            with LOCK:
                state["model"] = res
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
        al["active"] = al["streak"] >= ALERT_TICKS
        buzz = al["active"] and al["muted_until"] <= now and now - al["last_buzz"] >= 5
        req = state["vibe_request"]
        state["vibe_request"] = None
        if buzz:
            al["last_buzz"] = now
    if buzz and req is None:
        req = (500, 45)
    if req:
        try:
            Bridge.call("vibe", req[0], req[1])
        except Exception as e:
            print("vibe failed:", e, flush=True)


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

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            data = (HERE / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/api/state":
            self._json(200, snapshot())
        elif self.path == "/api/replay":
            rs = replay_state()
            if replay is not None and rs.get("active"):
                rs = {**rs, "cases": replay.cases(), "results": RESULTS_NOTE}
            else:
                rs = {**rs, "results": RESULTS_NOTE}
            self._json(200, rs)
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
        if self.path == "/vitals":
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
                replay.start(case, seconds_per_hour=sph)
            return self._json(200, {"ok": True})
        if self.path == "/replay/stop":
            if replay is not None:
                with REPLAY_LOCK:
                    replay.stop()
            return self._json(200, {"ok": True})
        if self.path == "/vibe":
            with LOCK:
                state["vibe_request"] = (400, 45)
            return self._json(200, {"ok": True})
        if self.path == "/ack":
            with LOCK:
                state["alert"]["muted_until"] = time.time() + ACK_MUTE_S
            return self._json(200, {"ok": True})
        self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve():
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


threading.Thread(target=serve, daemon=True).start()
print(f"dashboard + /vitals on port {PORT}", flush=True)


def loop():
    try:
        tick()
    except Exception as e:
        print("tick failed:", e, flush=True)
    time.sleep(1)


App.run(user_loop=loop)
