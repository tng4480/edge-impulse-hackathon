"""Liveness (is each part of the chain working?) and personal baseline. Context only: nothing here is scored.

Three separate states, because they fail separately:
  watch link   : are packets arriving from the watch?
  readings     : how old is each live vital, and is it stale?
  engine       : is the model running locally, and when did it last score?
A network check says whether the internet is reachable, so the dashboard can show
"offline: models running locally" while the LAN (watch to board) still works.

Fault fixtures (Faults) let a demo cut a part of the chain on purpose and clear it again.
"""
import json
import pathlib
import socket
import threading
import time
from collections import deque

# A reading turns grey after STALE_S; the board stops using it after the hold limits in main.py.
STALE_S = {"hr": 12, "rr": 12, "spo2": 300, "skin": 90, "hrv": 120}
WATCH_OK_S = 15          # last watch packet newer than this: link "connected"
WATCH_LOST_S = 60        # older than this: "disconnected"; in between "slow"
ENGINE_OK_S = 15         # last model score newer than this: engine "running"

REST_MOTION_G = 0.012    # chest IMU motion below this counts as resting
BASELINE_MIN_N = 10      # minute-level resting points needed to show a baseline
NOW_WINDOW_S = 600       # "now" = median of resting points in the last 10 min
TOD_HALF_WINDOW_S = 1800 # same time of day = within +-30 min of now, on an earlier day
KEEP_S = 7 * 86400


def _median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def age_info(age_s, name):
    if age_s is None:
        return {"age_s": None, "stale": False}
    return {"age_s": round(age_s, 1), "stale": age_s > STALE_S[name]}


class NetCheck:
    """Cheap connectivity check every 30 s on a background thread (never blocks the 1 s tick)."""

    def __init__(self, every_s=30):
        self.every_s = every_s
        self.lan = None
        self.internet = None
        self.checked_at = None
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def _lan_ok():
        # A UDP "connect" sends nothing; it only asks the OS which local address would be used.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return not ip.startswith("127.")
        except OSError:
            return False

    @staticmethod
    def _internet_ok():
        for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
            try:
                socket.create_connection((host, port), timeout=2).close()
                return True
            except OSError:
                continue
        return False

    def check(self):
        self.lan = self._lan_ok()
        self.internet = self._internet_ok() if self.lan else False
        self.checked_at = time.time()

    def _loop(self):
        while True:
            try:
                self.check()
            except Exception as e:  # a failed check must never kill the thread
                print("net check failed:", e, flush=True)
            time.sleep(self.every_s)

    def status(self, now, simulated_cut=False):
        if simulated_cut:
            return {"lan": self.lan, "internet": False, "simulated": True,
                    "checked_age_s": round(now - self.checked_at) if self.checked_at else None}
        return {"lan": self.lan, "internet": self.internet, "simulated": False,
                "checked_age_s": round(now - self.checked_at) if self.checked_at else None}


class Faults:
    """Deterministic fault fixtures for the demo. Each lasts `seconds` (or until cleared)."""

    KINDS = {
        "watch_drop": "watch link down (the board refuses watch packets; the watch buffers and retries)",
        "imu_freeze": "chest sensor frozen (no new samples; respiratory rate goes stale)",
        "internet_cut": "internet cut (simulated; the models never needed it)",
    }

    def __init__(self):
        self._until = {}

    def set(self, kind, seconds=60.0):
        if kind not in self.KINDS:
            raise ValueError(f"kind must be one of {sorted(self.KINDS)}")
        self._until[kind] = time.time() + max(5.0, min(600.0, float(seconds)))

    def clear(self, kind=None):
        if kind is None:
            self._until.clear()
        else:
            self._until.pop(kind, None)

    def active(self, kind):
        until = self._until.get(kind)
        if until is None:
            return False
        if time.time() >= until:
            self._until.pop(kind, None)
            return False
        return True

    def status(self):
        now = time.time()
        return {k: {"active": self.active(k), "seconds_left": round(self._until[k] - now) if k in self._until else 0,
                    "what": v} for k, v in self.KINDS.items()}


class Baseline:
    """Resting heart rate and HRV (RMSSD) against the wearer's own normal. Context only.

    Only readings taken while the chest IMU says the wearer is still are kept, one per minute.
    The baseline for "now" is the wearer's median at the same time of day on earlier days when
    there are enough points; otherwise the median of the previous hours (30 min to 6 h ago).
    Saved to disk every 5 minutes so it survives an app restart.
    """

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.series = {"hr": deque(maxlen=KEEP_S // 60), "hrv": deque(maxlen=KEEP_S // 60)}
        self._cur = {"hr": [], "hrv": []}
        self._minute = None
        self._saved = time.time()
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            now = time.time()
            for k in self.series:
                self.series[k].extend((t, v) for t, v in data.get(k, []) if now - t <= KEEP_S)
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            self.path.write_text(json.dumps({k: list(v) for k, v in self.series.items()}))
        except OSError as e:
            print("baseline save failed:", e, flush=True)

    def add(self, now, still, hr, rmssd):
        """Call once a second. hr / rmssd may be None."""
        if still:
            if hr is not None:
                self._cur["hr"].append(hr)
            if rmssd is not None:
                self._cur["hrv"].append(rmssd)
        minute = int(now // 60)
        if self._minute is None:
            self._minute = minute
        if minute != self._minute:
            t = self._minute * 60 + 30
            for k in ("hr", "hrv"):
                if self._cur[k]:
                    self.series[k].append((t, round(_median(self._cur[k]), 1)))
                self._cur[k] = []
            self._minute = minute
        if now - self._saved >= 300:
            self._saved = now
            self._save()

    def _now_value(self, kind, now):
        recent = [v for t, v in self.series[kind] if now - t <= NOW_WINDOW_S]
        return (round(_median(recent), 1), len(recent)) if len(recent) >= 3 else (None, len(recent))

    def _baseline(self, kind, now):
        pts = list(self.series[kind])
        same = [(t, v) for t, v in pts
                if t < now - 3600 and min((t - now) % 86400, (now - t) % 86400) <= TOD_HALF_WINDOW_S]
        if len(same) >= BASELINE_MIN_N:
            days = len({int(t // 86400) for t, _ in same})
            return round(_median([v for _, v in same]), 1), f"same time of day, {days} earlier day{'s' if days != 1 else ''}", len(same)
        prior = [v for t, v in pts if now - 6 * 3600 <= t <= now - 1800]
        if len(prior) >= BASELINE_MIN_N:
            return round(_median(prior), 1), "your previous hours (no earlier days yet)", len(prior)
        return None, f"learning ({len(prior)}/{BASELINE_MIN_N} resting minutes)", len(prior)

    def summary(self, now, still):
        out = {"still": still}
        for kind in ("hr", "hrv"):
            cur, n_cur = self._now_value(kind, now)
            base, basis, n_base = self._baseline(kind, now)
            out[kind] = {"now": cur, "baseline": base, "basis": basis, "n_base": n_base,
                         "delta": round(cur - base, 1) if cur is not None and base is not None else None,
                         "resting_now": cur is not None}
        return out
