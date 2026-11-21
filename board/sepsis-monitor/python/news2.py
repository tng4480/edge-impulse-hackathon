"""Partial NEWS2 (Royal College of Physicians, 2017) from the vitals we can measure.

Scored here: respiratory rate, SpO2 (scale 1), temperature, heart rate.
NOT available from the wearable, so scored 0: systolic BP, consciousness, supplemental O2.
A total of 5+ is NEWS2's "urgent response" trigger, and any single 3 is an "urgent ward-based response".
"""


def _band(value, bands):
    for lo, hi, pts in bands:
        if lo <= value <= hi:
            return pts
    return 0


RR = [(-1e9, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, 1e9, 3)]
SPO2 = [(-1e9, 91, 3), (92, 93, 2), (94, 95, 1), (96, 1e9, 0)]
TEMP = [(-1e9, 35.0, 3), (35.01, 36.0, 1), (36.01, 38.0, 0), (38.01, 39.0, 1), (39.01, 1e9, 2)]
HR = [(-1e9, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, 1e9, 3)]


def news2(rr=None, spo2=None, temp=None, hr=None):
    parts, missing = {}, []
    for name, value, bands in (("rr", rr, RR), ("spo2", spo2, SPO2), ("temp", temp, TEMP), ("hr", hr, HR)):
        if value is None:
            missing.append(name)
        else:
            parts[name] = _band(value, bands)
    total = sum(parts.values())
    return {"score": total, "parts": parts, "missing": missing, "any_red": any(p == 3 for p in parts.values())}
