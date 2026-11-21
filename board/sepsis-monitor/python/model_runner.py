"""Sepsis risk model on the board.

Engine 1 (primary): the Edge Impulse .eim (Linux aarch64), built from our LightGBM model via
BYOM, talking the Edge Impulse runner protocol (JSON over a Unix socket, replies end in a NUL).
Engine 2 (fallback): the same trees evaluated in pure Python from model/model.json, so the
demo never depends on the runner starting. Both give the same probability (checked to 4 dp).

    rm = RiskModel()                 # finds model/sepsis.eim and model/model.json
    rm.score(hourly)                 # hourly = [[HR, O2Sat, Temp, Resp], ...] oldest first
    -> {"risk": 0-100 or None, "alert": bool, "engine": "eim"|"trees", "hours": n, "note": str,
        "trend": {"HR": +12.0, ...}}   # 6 h change per vital, for "why flagged"

HourlyVitals turns the live 1 Hz vitals into hourly medians, the time base the model was trained on.
"""
import json
import math
import os
import pathlib
import socket
import subprocess
import tempfile
import time

from features import FEATURE_NAMES, MIN_HOURS, VITALS, features

HERE = pathlib.Path(__file__).parent
MODEL_DIR = HERE / "model"


class EimRunner:
    def __init__(self, path):
        os.chmod(path, 0o755)
        self._dir = tempfile.mkdtemp()
        sock = os.path.join(self._dir, "runner.sock")
        self._proc = subprocess.Popen([str(path), sock], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while not os.path.exists(sock):
            if self._proc.poll() is not None or time.time() - t0 > 20:
                raise RuntimeError(f"eim did not start (exit {self._proc.poll()})")
            time.sleep(0.1)
        self._s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._s.settimeout(10)
        self._s.connect(sock)
        self._id = 0
        self.info = self._send({"hello": 1})

    def _send(self, msg):
        self._id += 1
        msg["id"] = self._id
        self._s.sendall(json.dumps(msg).encode())
        data = b""
        while True:
            chunk = self._s.recv(4096)
            if not chunk:
                raise RuntimeError("eim closed the socket")
            if chunk[-1] == 0:
                data += chunk[:-1]
                break
            data += chunk
        text = data.decode()
        return json.loads(text[text.index("{"):text.rindex("}") + 1])

    def p_sepsis(self, fv):
        r = self._send({"classify": [float(v) for v in fv]})
        if not r.get("success", True):
            raise RuntimeError(r.get("error"))
        return float(r["result"]["classification"]["sepsis"])

    def close(self):
        try:
            self._proc.terminate()
        except Exception:
            pass


class Trees:
    """Evaluates a LightGBM binary model from its JSON dump (booster.dump_model())."""

    def __init__(self, path):
        m = json.loads(pathlib.Path(path).read_text())
        self.trees = [t["tree_structure"] for t in m["tree_info"]]

    @staticmethod
    def _leaf(node, x):
        while "leaf_value" not in node:
            v = x[node["split_feature"]]
            if v is None or (isinstance(v, float) and math.isnan(v)):
                go_left = node.get("default_left", True)
            else:
                go_left = v <= node["threshold"]
            node = node["left_child"] if go_left else node["right_child"]
        return node["leaf_value"]

    def p_sepsis(self, fv):
        raw = sum(self._leaf(t, fv) for t in self.trees)
        return 1.0 / (1.0 + math.exp(-raw))


class RiskModel:
    def __init__(self, model_dir=MODEL_DIR):
        meta = json.loads((model_dir / "meta.json").read_text())
        assert meta["features"] == FEATURE_NAMES, "feature list mismatch between model and features.py"
        self.threshold = meta["threshold"]
        self.engine, self.note = None, ""
        eim = model_dir / "sepsis.eim"
        if eim.exists():
            try:
                self.engine = EimRunner(eim)
                self.name = "eim"
            except Exception as e:
                self.note = f"eim failed ({e}); using tree fallback"
        if self.engine is None:
            self.engine = Trees(model_dir / "model.json")
            self.name = "trees"

    def score(self, hourly):
        n = len(hourly)
        out = {"risk": None, "alert": False, "engine": self.name, "hours": n,
               "threshold": round(self.threshold * 100, 1), "note": self.note, "trend": {}}
        fv = features(hourly)
        if fv is None:
            out["note"] = f"collecting hourly history ({n}/{MIN_HOURS} h)"
            return out
        p = self.engine.p_sepsis(fv)
        out["risk"] = round(p * 100, 1)
        out["alert"] = p >= self.threshold
        for v in VITALS:  # 6 h change, the most readable "why"
            out["trend"][v] = round(fv[FEATURE_NAMES.index(f"{v}_d6")], 2)
        return out


class HourlyVitals:
    """Collects live readings and emits one median row per clock hour (max 48 h kept)."""

    def __init__(self, keep_hours=48):
        self.keep = keep_hours
        self.rows = []          # completed hours: [HR, O2Sat, Temp, Resp]
        self.cur_hour = None
        self.cur = {v: [] for v in VITALS}

    def add(self, now, hr=None, spo2=None, temp=None, rr=None):
        hour = int(now // 3600)
        if self.cur_hour is not None and hour != self.cur_hour:
            self.rows.append(self._median_row())
            # Hours with no readings at all (watch off, board unplugged) become empty rows,
            # as in the PhysioNet training data, so trend features see the real time gap.
            gap = min(max(0, hour - self.cur_hour - 1), self.keep)
            self.rows.extend([[None] * len(VITALS)] * gap)
            self.rows = self.rows[-self.keep:]
            self.cur = {v: [] for v in VITALS}
        self.cur_hour = hour
        for v, x in zip(VITALS, (hr, spo2, temp, rr)):
            if x is not None:
                self.cur[v].append(float(x))

    def _median_row(self):
        row = []
        for v in VITALS:
            xs = sorted(self.cur[v])
            row.append(xs[len(xs) // 2] if xs else None)
        return row

    def history(self):
        """Completed hours plus the current partial hour."""
        return self.rows + [self._median_row()]
