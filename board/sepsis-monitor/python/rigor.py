"""Shaking-chill (rigor) detector from the chest accelerometer: band energy, no trained model.

Shivering and rigors show up as a sustained tremor of about 4-8 Hz. Breathing is below 1 Hz and
walking is a 1.5-2.5 Hz rhythm, so the detector asks two questions of each 4 s window:

  1. Is there enough 4-8 Hz energy (rms in g) to be more than sensor noise?
  2. Does that band hold most of the movement energy, rather than the 0.7-3 Hz walking band?

A window that passes both is "shaky". The alert needs most of the last 12 windows to be shaky, so
one hand wave or a cough does not trigger it. The thresholds are starting values from synthetic
signals, NOT calibrated on real chills: record a few minutes of rest, walking and acted shivering
with rigor_check.py and adjust SHAKE_MIN_G / SHAKE_RATIO before trusting it.

It never scores sepsis. The device asks the wearer "are you having chills?" and a person decides.
"""
import math

FS = 25.0
WIN_S = 4.0
BAND_LOW = (0.7, 3.0)      # walking and body movement
BAND_SHAKE = (4.0, 8.0)    # tremor
SHAKE_MIN_G = 0.012        # band rms below this is noise
SHAKE_RATIO = 0.60         # share of (low + shake) energy that must sit in the tremor band
HISTORY = 12               # one window per second
ON_COUNT, OFF_COUNT = 8, 4  # shaky windows needed to switch on / stay on


def _band_rms(x, fs, lo, hi):
    """rms (g) of x between lo and hi Hz, from a DFT at 0.25 Hz resolution via the Goertzel recursion."""
    n = len(x)
    total = 0.0
    f = lo
    while f <= hi + 1e-9:
        k = f * n / fs                       # fractional bin: fine for a band-energy estimate
        w = 2 * math.pi * k / n
        c = 2 * math.cos(w)
        s1 = s2 = 0.0
        for v in x:
            s0 = v + c * s1 - s2
            s2, s1 = s1, s0
        power = s1 * s1 + s2 * s2 - c * s1 * s2          # |X_k|^2
        amp = 2 * math.sqrt(max(power, 0.0)) / n          # sinusoid amplitude at f
        total += amp * amp / 2                            # its mean-square
        f += 0.25
    return math.sqrt(total)


def window_features(ax, ay, az, fs=FS):
    """(shake_rms_g, low_rms_g, ratio) for the newest WIN_S seconds, or None if too short."""
    n = int(WIN_S * fs)
    if len(ax) < n:
        return None
    mag = [(x * x + y * y + z * z) ** 0.5 for x, y, z in zip(ax[-n:], ay[-n:], az[-n:])]
    mean = sum(mag) / n
    mag = [v - mean for v in mag]
    # Hann window: stops a strong low-frequency rhythm leaking into the tremor band
    mag = [v * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) for i, v in enumerate(mag)]
    gain = math.sqrt(8 / 3)                               # restores rms lost to the Hann window
    shake = _band_rms(mag, fs, *BAND_SHAKE) * gain
    low = _band_rms(mag, fs, *BAND_LOW) * gain
    ratio = shake ** 2 / (shake ** 2 + low ** 2) if shake + low > 0 else 0.0
    return shake, low, ratio


class RigorDetector:
    """Call update() once a second with the recent accelerometer lists (newest last)."""

    def __init__(self):
        self.flags = []
        self.on = False
        self.since = None
        self.last = {"shaking": False, "shake_g": None, "ratio": None, "since": None, "reason": "warming up"}

    def update(self, now, ax, ay, az, fs=FS):
        f = window_features(ax, ay, az, fs)
        if f is None:
            self.last = {"shaking": False, "shake_g": None, "ratio": None, "since": None, "reason": "warming up"}
            return self.last
        shake, low, ratio = f
        self.flags = (self.flags + [shake >= SHAKE_MIN_G and ratio >= SHAKE_RATIO])[-HISTORY:]
        hits = sum(self.flags)
        if not self.on and hits >= ON_COUNT:
            self.on, self.since = True, now
        elif self.on and hits < OFF_COUNT:
            self.on, self.since = False, None
        reason = "shaking" if self.on else ("tremor-like, confirming" if self.flags[-1] else "none")
        self.last = {"shaking": self.on, "shake_g": round(shake, 4), "ratio": round(ratio, 2),
                     "since": self.since, "reason": reason}
        return self.last
