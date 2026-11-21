"""Trend features for the sepsis model. Pure Python so the board and training share this exact code.

Input: hourly records, oldest first, each [HR, O2Sat, Temp, Resp] (None = missing).
Missing values are carried forward from the last known value; a vital never seen
uses the population median. Uses the last up-to-24 hours; needs at least MIN_HOURS.
"""
VITALS = ("HR", "O2Sat", "Temp", "Resp")
WINDOW_H = 24
MIN_HOURS = 8
# PhysioNet 2019 training-set medians, used only when a vital has never been seen.
DEFAULTS = {"HR": 84.0, "O2Sat": 98.0, "Temp": 36.9, "Resp": 18.0}

FEATURE_NAMES = [f"{v}_{s}" for v in VITALS
                 for s in ("last", "mean", "min", "max", "std", "d1", "d6", "slope")]


def _fill(series, default):
    out, last = [], None
    for v in series:
        if v is not None and v == v:  # not None, not NaN
            last = v
        out.append(last)
    first = next((v for v in out if v is not None), default)
    return [first if v is None else v for v in out]


def _slope(x):
    n = len(x)
    if n < 3:
        return 0.0
    mt = (n - 1) / 2
    mx = sum(x) / n
    num = sum((i - mt) * (v - mx) for i, v in enumerate(x))
    den = sum((i - mt) ** 2 for i in range(n))
    return num / den


def features(hourly):
    """hourly: list of [HR, O2Sat, Temp, Resp]. Returns a list of len(FEATURE_NAMES) floats, or None."""
    if len(hourly) < MIN_HOURS:
        return None
    filled = [_fill([row[i] for row in hourly], DEFAULTS[v]) for i, v in enumerate(VITALS)]
    out = []
    for x in filled:
        x = x[-WINDOW_H:]
        n = len(x)
        mean = sum(x) / n
        std = (sum((v - mean) ** 2 for v in x) / n) ** 0.5
        out += [x[-1], mean, min(x), max(x), std,
                x[-1] - x[-2], x[-1] - x[max(0, n - 7)], _slope(x)]
    return out
