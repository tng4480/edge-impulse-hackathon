"""Pulse arrival time (PAT) from the Galaxy Watch's ECG and green PPG. numpy only.

The Samsung ECG tracker delivers both signals in the same packets (one timestamp per 20 ms packet:
10 ECG samples at 500 Hz and 2 PPG samples at 100 Hz), so they share a clock. PAT is the time from
the ECG R-peak to the steepest upstroke of the pulse wave at the wrist.

CONTEXT ONLY. PAT includes the heart's pre-ejection period and moves with arm height, posture and
motion. It is not a blood pressure and the device never scores it. Needs a finger on the watch's
top button; the tracker runs about 30 s per check.

    s = PatSession()
    s.add_chunk({"pt": [...ms per packet], "ecg": [10 per packet], "ppg": [2 per packet, -1 = none],
                 "lead": [per packet, 0 = finger on]})
    s.analyse()  -> dict for /api/pat
"""
import time

import numpy as np

ECG_HZ, PPG_HZ = 500, 100
KEEP_S = 40                  # seconds of signal kept
SHOW_S = 8                   # seconds of waveform returned to the page
PAT_RANGE_MS = (80, 450)
MAX_PACKETS_PER_CHUNK = 200  # 4 s; the watch sends about 50 per second


def _ma(x, n):
    n = max(1, int(n))
    if n == 1 or len(x) < n:
        return np.asarray(x, float)
    k = np.ones(n) / n
    pad = np.pad(x, (n // 2, n - 1 - n // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")


def validate_chunk(body):
    """(clean chunk, errors) for POST /api/ecg."""
    if not isinstance(body, dict):
        return None, ["body is not a JSON object"]
    pt, ecg, ppg, lead = (body.get(k) for k in ("pt", "ecg", "ppg", "lead"))
    for name, v in (("pt", pt), ("ecg", ecg), ("ppg", ppg), ("lead", lead)):
        if not isinstance(v, list) or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in v):
            return None, [f"{name} must be a list of numbers"]
    n = len(pt)
    if not 1 <= n <= MAX_PACKETS_PER_CHUNK:
        return None, [f"pt must hold 1 to {MAX_PACKETS_PER_CHUNK} packets"]
    if len(ecg) != 10 * n or len(ppg) != 2 * n or len(lead) != n:
        return None, ["need 10 ecg samples, 2 ppg samples and 1 lead flag per packet"]
    if any(b <= a for a, b in zip(pt, pt[1:])):
        return None, ["pt must increase"]
    return {"pt": [float(x) for x in pt], "ecg": [float(x) for x in ecg],
            "ppg": [float(x) for x in ppg], "lead": [int(x) for x in lead]}, []


class PatSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.te, self.ecg, self.tp, self.ppg, self.lead_t, self.lead = [], [], [], [], [], []
        self.updated = None
        self.baseline_ms = None

    def add_chunk(self, c, now=None):
        for i, t in enumerate(c["pt"]):
            for k in range(10):
                self.te.append(t / 1000.0 + 0.002 * k)
                self.ecg.append(c["ecg"][10 * i + k])
            for k in (0, 1):
                v = c["ppg"][2 * i + k]
                if v >= 0:
                    self.tp.append(t / 1000.0 + 0.010 * k)   # 100 Hz: the two PPG samples sit at +0 and +10 ms
                    self.ppg.append(v)
            self.lead_t.append(t / 1000.0)
            self.lead.append(c["lead"][i])
        cut = self.te[-1] - KEEP_S
        while self.te and self.te[0] < cut:
            self.te.pop(0); self.ecg.pop(0)
        while self.tp and self.tp[0] < cut:
            self.tp.pop(0); self.ppg.pop(0)
        while self.lead_t and self.lead_t[0] < cut:
            self.lead_t.pop(0); self.lead.pop(0)
        self.updated = time.time() if now is None else now

    # ---- analysis ------------------------------------------------------------------------------
    @staticmethod
    def r_peaks(t, x):
        """R-peak times and the band-passed trace. Pan-Tompkins style with an adaptive threshold."""
        band = _ma(x, 5) - _ma(x, 100)                       # about 5-40 Hz
        feat = _ma(np.gradient(band) ** 2, 40)               # 80 ms integration
        if len(feat) < ECG_HZ * 3:
            return np.array([]), band
        # Local threshold: a fraction of the strongest energy within about +-1.5 s, so one noisy
        # stretch at the start (finger settling) cannot hide the clean beats that follow.
        blk = ECG_HZ // 2
        nb = int(np.ceil(len(feat) / blk))
        bmax = np.array([feat[i * blk:(i + 1) * blk].max() for i in range(nb)])
        roll = np.array([bmax[max(0, i - 3):i + 4].max() for i in range(nb)])
        thr = 0.3 * np.repeat(roll, blk)[:len(feat)]
        cand = np.where((feat[1:-1] > feat[:-2]) & (feat[1:-1] >= feat[2:]) & (feat[1:-1] > thr[1:-1]))[0] + 1
        peaks, last = [], -1
        for i in cand:
            if last >= 0 and i - last < 0.30 * ECG_HZ:
                if feat[i] > feat[last]:
                    peaks[-1] = i; last = i
                continue
            peaks.append(i); last = i
        out = []
        for i in peaks:                                      # snap to the sharpest deflection near the energy peak
            a, b = max(0, i - 40), min(len(band), i + 40)
            out.append(a + int(np.argmax(np.abs(band[a:b]))))
        return np.array(sorted(set(out)), int), band

    @staticmethod
    def ppg_wave(tp, ppg, t_lo, t_hi):
        """PPG resampled to 100 Hz, smoothed, trend removed. Returns (grid, signal, slope sign)."""
        grid = np.arange(t_lo, t_hi, 1.0 / PPG_HZ)
        if len(tp) < 50 or len(grid) < 100:
            return grid, np.zeros(len(grid)), 1
        v = np.asarray(ppg, float)
        v = np.clip(v, *np.percentile(v, [1, 99]))
        y = np.interp(grid, tp, v)
        y = _ma(y, 5) - _ma(y, PPG_HZ)
        d = np.gradient(y)
        sign = 1 if np.percentile(d, 99) >= -np.percentile(d, 1) else -1   # the steeper stroke is the upstroke
        return grid, y, sign

    @staticmethod
    def _beats(rt, touched, grid, d):
        """One PAT per R-peak: time to the steepest slope of d in the allowed window."""
        floor = 0.3 * np.percentile(d, 95) if len(d) else 0
        beats = []
        for r, ok in zip(rt, touched):
            if not ok:
                continue
            w = (grid > r + PAT_RANGE_MS[0] / 1000) & (grid < r + PAT_RANGE_MS[1] / 1000)
            if w.sum() < 5:
                continue
            j = int(np.argmax(d[w]))
            if d[w][j] < floor:
                continue
            beats.append({"t": float(r), "foot": float(grid[w][j]), "pat_ms": round(float((grid[w][j] - r) * 1000), 1)})
        return beats

    def analyse(self, now=None):
        now = time.time() if now is None else now
        out = {"active": False, "age_s": None if self.updated is None else round(now - self.updated, 1),
               "finger": None, "hr": None, "beats": [], "pat_ms": None, "pat_spread_ms": None,
               "baseline_ms": self.baseline_ms, "delta_ms": None, "n_beats": 0,
               "wave": None, "note": "no ECG check yet"}
        if self.updated is None:
            return out
        out["active"] = now - self.updated < 3
        out["finger"] = bool(self.lead) and self.lead[-1] == 0
        t = np.asarray(self.te)
        if len(t) < ECG_HZ * 6:
            out["note"] = "collecting signal"
            return out
        x = np.asarray(self.ecg)
        ri, band = self.r_peaks(t, x)
        rt = t[ri]
        lt, lv = np.asarray(self.lead_t), np.asarray(self.lead)
        touched = np.array([lv[np.argmin(np.abs(lt - r))] == 0 for r in rt]) if len(rt) else np.array([], bool)
        grid, y, _ = self.ppg_wave(self.tp, self.ppg, t[0], t[-1])
        # Which stroke of the green-PPG trace is "arrival" depends on the sensor's polarity, so try
        # both steepest-slope landmarks and keep the one that repeats more tightly beat to beat.
        best = None
        for sign in (1, -1):
            beats = self._beats(rt, touched, grid, sign * np.gradient(y))
            if len(beats) >= 5:
                med = float(np.median([b["pat_ms"] for b in beats]))
                mad = float(np.median([abs(b["pat_ms"] - med) for b in beats])) or 5.0
                beats = [b for b in beats if abs(b["pat_ms"] - med) <= max(25.0, 4 * mad)]
                mad = float(np.median([abs(b["pat_ms"] - np.median([c["pat_ms"] for c in beats])) for b in beats])) if beats else 99
            else:
                mad = 99
            if best is None or (len(beats) >= 5 and mad < best[0]):
                best = (mad, sign, beats)
        _, sign, beats = best
        out["n_beats"] = len(beats)
        if len(rt) >= 3:
            rr = np.diff(rt)
            rr = rr[(rr > 0.35) & (rr < 1.6)]
            if len(rr):
                out["hr"] = round(60 / float(np.median(rr)), 0)
        recent = [b["pat_ms"] for b in beats[-12:]]
        if len(recent) >= 4:
            out["pat_ms"] = round(float(np.median(recent)), 0)
            out["pat_spread_ms"] = round(float(np.median([abs(v - np.median(recent)) for v in recent])), 1)
            if self.baseline_ms is None and len(beats) >= 10:
                self.baseline_ms = round(float(np.median([b["pat_ms"] for b in beats[:10]])), 0)
                out["baseline_ms"] = self.baseline_ms
            if self.baseline_ms is not None:
                out["delta_ms"] = round(out["pat_ms"] - self.baseline_ms, 0)
            out["note"] = "ok"
        else:
            out["note"] = "finger on the top button, keep still" if not out["finger"] else "settling"
        # waveform for the page, times relative to now (seconds, negative = past)
        t_end = t[-1]
        m = t > t_end - SHOW_S
        mg = grid > t_end - SHOW_S
        out["wave"] = {
            "ecg_t": [round(float(v - t_end), 3) for v in t[m][::4]],
            "ecg": [round(float(v), 3) for v in band[m][::4]],
            "ppg_t": [round(float(v - t_end), 3) for v in grid[mg]],
            "ppg": [round(float(v * sign), 1) for v in y[mg]],
            "r": [round(b["t"] - t_end, 3) for b in beats if b["t"] > t_end - SHOW_S],
            "foot": [round(b["foot"] - t_end, 3) for b in beats if b["t"] > t_end - SHOW_S],
        }
        out["beats"] = [{"pat_ms": b["pat_ms"]} for b in beats[-20:]]
        return out
