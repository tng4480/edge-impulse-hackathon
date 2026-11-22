"""Respiratory rate from a chest-mounted accelerometer. Pure Python, no numpy.

Breathing moves the chest at roughly 0.1-0.6 Hz (6-36 breaths/min). The
accelerometer also sees gravity (DC) and any body motion (faster than breathing),
so: band-pass the signal, clip one-off movements, find the breathing period by
autocorrelation, and refuse to answer while the wearer is moving.
"""
FS = 25.0                 # Hz, set by the sketch (40 ms sample period)
MIN_SECONDS = 20          # need this much data before answering
WINDOW_S = 30             # analyse the most recent 30 s
MIN_STRENGTH = 0.30       # autocorrelation peak needed to trust the rhythm
MOTION_STD_G = 0.03       # fast-motion std above this => gated (walking, talking)
MIN_AMPLITUDE_G = 0.0008  # band-passed std below this => just sensor noise
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


def _bandpass(x, fs):
    low = _moving_average(x, fs * 0.7)    # keeps < ~0.6 Hz
    slow = _moving_average(x, fs * 10.0)  # removes < ~0.1 Hz
    return [a - b for a, b in zip(low, slow)], low


def _clip(x):
    """Tame one-off movements: clip at 4 robust sigmas (MAD-based) around the median."""
    s = sorted(x)
    med = s[len(s) // 2]
    mad = sorted(abs(v - med) for v in x)[len(x) // 2]
    sigma = 1.4826 * mad
    if sigma <= 0:
        return [0.0] * len(x), 0.0
    lim = 4 * sigma
    return [max(-lim, min(lim, v - med)) for v in x], sigma


def estimate_rr(ax, ay, az, fs=FS):
    """ax, ay, az: equal-length lists in g (newest last). Returns a dict:
    rr (breaths/min or None), reason (why None), motion_g, amplitude_g, strength (0-1).

    Uses the last WINDOW_S seconds. Each axis is band-passed to the breathing band,
    outliers are clipped, and the breathing period is the lag of the strongest
    autocorrelation peak (summed over axes). That keeps working when heartbeat
    or small shifts make the breaths uneven, which peak counting does not.
    """
    n_win = int(WINDOW_S * fs)
    ax, ay, az = ax[-n_win:], ay[-n_win:], az[-n_win:]
    n = len(ax)
    if n < MIN_SECONDS * fs:
        return {"rr": None, "reason": "warming up", "motion_g": None, "amplitude_g": None, "strength": None}

    mag = [(x * x + y * y + z * z) ** 0.5 for x, y, z in zip(ax, ay, az)]
    low = _moving_average(mag, fs * 0.7)
    motion = _std([m - l for m, l in zip(mag, low)])
    if motion > MOTION_STD_G:
        return {"rr": None, "reason": "moving", "motion_g": round(motion, 4), "amplitude_g": None, "strength": None}

    chans, sigmas = [], []
    for axis in (ax, ay, az):
        bp, _ = _bandpass(axis, fs)
        c, sg = _clip(bp)
        chans.append(c)
        sigmas.append(sg)
    amp = max(sigmas)
    if amp < MIN_AMPLITUDE_G:
        return {"rr": None, "reason": "no breathing signal", "motion_g": round(motion, 4),
                "amplitude_g": round(amp, 5), "strength": None}

    lag_min = int(fs * 60 / RR_RANGE[1])   # fastest breathing
    lag_max = int(fs * 60 / RR_RANGE[0])   # slowest breathing
    energy = sum(v * v for c in chans for v in c)
    ac = {}
    for lag in range(lag_min - 1, lag_max + 2):
        tot = 0.0
        for c in chans:
            tot += sum(c[i] * c[i + lag] for i in range(n - lag))
        ac[lag] = tot / energy * n / (n - lag)   # unbiased: do not favour short lags
    lags = range(lag_min, lag_max + 1)
    peaks = [l for l in lags if ac[l] > ac[l - 1] and ac[l] >= ac[l + 1] and ac[l] > 0]
    if not peaks:
        return {"rr": None, "reason": "no rhythm", "motion_g": round(motion, 4),
                "amplitude_g": round(amp, 5), "strength": 0.0}
    best = max(ac[l] for l in peaks)
    # earliest strong peak: avoids reporting half the true rate when 2 breaths line up better
    lag = next(l for l in peaks if ac[l] >= 0.85 * best)
    strength = ac[lag]
    if strength < MIN_STRENGTH:
        return {"rr": None, "reason": "no clear rhythm", "motion_g": round(motion, 4),
                "amplitude_g": round(amp, 5), "strength": round(strength, 2)}
    rr = 60.0 * fs / lag
    return {"rr": round(rr, 1), "reason": "ok", "motion_g": round(motion, 4),
            "amplitude_g": round(amp, 5), "strength": round(strength, 2)}


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
