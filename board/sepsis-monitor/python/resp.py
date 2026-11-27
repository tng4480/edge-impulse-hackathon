"""Respiratory rate from a chest-mounted accelerometer. Pure Python, no numpy.

Breathing tilts/moves the chest at roughly 0.1-0.67 Hz (6-40 breaths/min) with
an amplitude of only a few milli-g, while small posture shifts produce 50-150 mg
step changes in gravity projection. To stay usable in real wear:
  1. Gate fast body motion (walking, talking) via high-passed magnitude std.
  2. Suppress sudden posture steps by MAD-clipping the first difference before
     filtering, then re-integrating (eliminates step-response filter ringing).
  3. Zero-phase 2nd-order Butterworth low-pass (0.70 Hz), downsample to 5 Hz,
     and zero-phase high-pass (0.10 Hz).
  4. Score each axis independently (so a noisy axis cannot swamp a clean one)
     using Hann-windowed spectral concentration plus normalized autocorrelation
     at the candidate breathing period.
"""
import math

FS = 25.0                 # Hz, set by the sketch (40 ms sample period)
MIN_SECONDS = 12          # need this much data before answering (~2.5-4 breaths)
WINDOW_S = 20             # analyse the most recent 20 s (recovers quickly after movement)
MIN_STRENGTH = 0.42       # spectral concentration (+-2 bpm around peak) needed to trust rhythm
MIN_AC = 0.35             # normalized autocorrelation at the candidate period (rejects single bumps)
MOTION_STD_G = 0.04       # fast-motion std above this => gated (walking, talking)
MIN_AMPLITUDE_G = 0.0008  # band-passed robust std below this => just sensor noise
RR_RANGE = (6.0, 40.0)


def _moving_average(x, n):
    n = max(1, int(n))
    cs = [0.0]
    for v in x:
        cs.append(cs[-1] + v)
    out = []
    for i in range(len(x)):
        a = max(0, i - n // 2)
        b = min(len(x), i + n // 2 + 1)
        out.append((cs[b] - cs[a]) / (b - a))
    return out


def _std(x):
    m = sum(x) / len(x)
    return (sum((v - m) ** 2 for v in x) / len(x)) ** 0.5


def _biquad_filtfilt(x, b0, b1, b2, a1, a2, init_zero=False):
    """Zero-phase forward-backward 2nd-order IIR filter with reflect padding."""
    n = len(x)
    if n < 4:
        return list(x)
    pad = min(15, n - 1)
    left = [2.0 * x[0] - x[i] for i in range(pad, 0, -1)]
    right = [2.0 * x[-1] - x[n - 1 - i] for i in range(1, pad + 1)]
    padded = left + list(x) + right
    m = len(padded)

    def run(seq):
        y = [0.0] * m
        x1 = x2 = seq[0]
        y1 = y2 = 0.0 if init_zero else seq[0]
        for i, v in enumerate(seq):
            o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            y[i] = o
            x2, x1 = x1, v
            y2, y1 = y1, o
        return y

    fwd = run(padded)
    rev = run(fwd[::-1])[::-1]
    return rev[pad:pad + n]


def _butter_lp(x, fc, fs):
    w0 = 2.0 * math.pi * fc / fs
    c, s = math.cos(w0), math.sin(w0)
    alpha = s / (2.0 ** 0.5)
    a0 = 1.0 + alpha
    return _biquad_filtfilt(
        x, (1.0 - c) / (2.0 * a0), (1.0 - c) / a0, (1.0 - c) / (2.0 * a0),
        (-2.0 * c) / a0, (1.0 - alpha) / a0, init_zero=False,
    )


def _butter_hp(x, fc, fs):
    w0 = 2.0 * math.pi * fc / fs
    c, s = math.cos(w0), math.sin(w0)
    alpha = s / (2.0 ** 0.5)
    a0 = 1.0 + alpha
    return _biquad_filtfilt(
        x, (1.0 + c) / (2.0 * a0), -(1.0 + c) / a0, (1.0 + c) / (2.0 * a0),
        (-2.0 * c) / a0, (1.0 - alpha) / a0, init_zero=True,
    )


def _clip(x, k=3.0):
    """Tame one-off movements: clip at k robust sigmas (MAD-based) around the median."""
    s = sorted(x)
    med = s[len(s) // 2]
    mad = sorted(abs(v - med) for v in x)[len(x) // 2]
    sigma = 1.4826 * mad
    if sigma <= 0:
        return [0.0] * len(x), 0.0
    lim = k * sigma
    return [max(-lim, min(lim, v - med)) for v in x], sigma


def _despike_steps(x, k=3.0):
    """Clip sudden posture-shift jumps in the first difference and re-integrate."""
    dx = [x[i] - x[i - 1] for i in range(1, len(x))]
    dx_c, _ = _clip(dx, k)
    out = [0.0] * len(x)
    acc = 0.0
    for i, d in enumerate(dx_c, 1):
        acc += d
        out[i] = acc
    return out


def estimate_rr(ax, ay, az, fs=FS):
    """ax, ay, az: equal-length lists in g (newest last). Returns a dict:
    rr (breaths/min or None), reason (why None), motion_g, amplitude_g, strength (0-1).
    """
    n_win = int(WINDOW_S * fs)
    ax, ay, az = ax[-n_win:], ay[-n_win:], az[-n_win:]
    n = len(ax)
    if n < MIN_SECONDS * fs:
        return {"rr": None, "reason": "warming up", "motion_g": None, "amplitude_g": None, "strength": None}

    mag = [(x * x + y * y + z * z) ** 0.5 for x, y, z in zip(ax, ay, az)]
    low_m = _butter_lp(mag, 0.7, fs)
    motion = _std([m - l for m, l in zip(mag, low_m)])
    if motion > MOTION_STD_G:
        return {"rr": None, "reason": "moving", "motion_g": round(motion, 4), "amplitude_g": None, "strength": None}

    dec = max(1, int(round(fs / 5.0)))
    fs_d = fs / dec
    chans, sigmas = [], []
    for axis in (ax, ay, az):
        clean = _despike_steps(axis, k=3.0)
        lp = _butter_lp(clean, 0.70, fs)[::dec]
        bp = _butter_hp(lp, 0.10, fs_d)
        c, sg = _clip(bp, k=3.0)
        chans.append(c)
        sigmas.append(sg)
    amp = max(sigmas)
    if amp < MIN_AMPLITUDE_G:
        return {"rr": None, "reason": "no breathing signal", "motion_g": round(motion, 4),
                "amplitude_g": round(amp, 5), "strength": None}

    m = len(chans[0])
    win = [0.5 * (1.0 - math.cos(2.0 * math.pi * i / (m - 1))) for i in range(m)]
    bpms = [RR_RANGE[0] + 0.5 * k for k in range(int((RR_RANGE[1] - RR_RANGE[0]) * 2) + 1)]
    best = None  # (score, rr_bpm, conc, ac_val)
    for c, sg in zip(chans, sigmas):
        if sg < MIN_AMPLITUDE_G * 0.75:
            continue
        cw = [v * w for v, w in zip(c, win)]
        spec = []
        tot_p = 0.0
        for bpm in bpms:
            f = bpm / 60.0
            w_step = 2.0 * math.pi * f / fs_d
            re = sum(cw[i] * math.cos(w_step * i) for i in range(m))
            im = sum(cw[i] * math.sin(w_step * i) for i in range(m))
            p = re * re + im * im
            spec.append(p)
            tot_p += p
        if tot_p <= 0:
            continue
        pk_i = max(range(len(spec)), key=lambda i: spec[i])
        pk_bpm = bpms[pk_i]
        if 0 < pk_i < len(spec) - 1:
            y0, y1, y2 = spec[pk_i - 1], spec[pk_i], spec[pk_i + 1]
            denom = y0 - 2.0 * y1 + y2
            if denom < 0:
                pk_bpm += 0.25 * (y0 - y2) / denom
        pk_bpm = max(RR_RANGE[0], min(RR_RANGE[1], pk_bpm))
        near_p = sum(p for p, b in zip(spec, bpms) if abs(b - pk_bpm) <= 2.0)
        conc = near_p / tot_p
        lag = int(round(60.0 * fs_d / pk_bpm))
        en = sum(v * v for v in c)
        ac_val = 0.0
        if 1 <= lag < m - 2 and en > 0:
            ac_val = sum(c[i] * c[i + lag] for i in range(m - lag)) / en * m / (m - lag)
        score = 0.5 * conc + 0.5 * max(0.0, ac_val)
        if best is None or score > best[0]:
            best = (score, pk_bpm, conc, ac_val)

    if best is None or best[2] < MIN_STRENGTH or best[3] < MIN_AC:
        return {"rr": None, "reason": "no clear rhythm", "motion_g": round(motion, 4),
                "amplitude_g": round(amp, 5), "strength": round(best[2], 2) if best else 0.0}
    return {"rr": round(best[1], 1), "reason": "ok", "motion_g": round(motion, 4),
            "amplitude_g": round(amp, 5), "strength": round(best[2], 2)}


def motion_level(ax, ay, az, fs=FS, seconds=10):
    """Fast-motion level (std of the magnitude minus its 0.7 s moving average, in g) over the last
    `seconds`. Returns None until there is enough data. Used to tell "resting" from "moving"."""
    n = int(seconds * fs)
    ax, ay, az = ax[-n:], ay[-n:], az[-n:]
    if len(ax) < n * 0.6:
        return None
    mag = [(x * x + y * y + z * z) ** 0.5 for x, y, z in zip(ax, ay, az)]
    low = _moving_average(mag, fs * 0.7)
    return _std([m - l for m, l in zip(mag, low)])
