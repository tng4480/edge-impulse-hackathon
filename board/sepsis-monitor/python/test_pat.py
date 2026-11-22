"""Checks for pat.py. Run: python test_pat.py   (needs numpy)."""
import json
import math
import pathlib
import random
import unittest

import pat

SAMPLE = pathlib.Path(__file__).resolve().parent / "model" / "ecg_sample.json"


def chunks(fx, per=50):
    n = len(fx["pt"])
    for a in range(0, n, per):
        b = min(n, a + per)
        yield {"pt": fx["pt"][a:b], "ecg": fx["ecg"][10 * a:10 * b], "ppg": fx["ppg"][2 * a:2 * b], "lead": fx["lead"][a:b]}


def synthetic(seconds=25, hr=75, pat_ms=210, seed=3, finger=True):
    """ECG with sharp QRS spikes, PPG pulses whose steepest rise follows each R by pat_ms."""
    rnd = random.Random(seed)
    n = int(seconds * 50)
    pt = [20 * i for i in range(n)]
    period = 60.0 / hr
    ecg, ppg = [], []
    for i in range(n):
        for k in range(10):
            t = (20 * i + 2 * k) / 1000.0
            ph = t % period
            ecg.append(310 + 0.8 * math.exp(-((ph - 0.05) / 0.012) ** 2) + rnd.gauss(0, 0.02))
        for k in (0, 5):
            t = (20 * i + 2 * k) / 1000.0
            ph = (t - pat_ms / 1000.0) % period
            ppg.append(int(50000 - 3000 * (1 / (1 + math.exp(-(ph - 0.05) / 0.02))) * math.exp(-ph / 0.35) + rnd.gauss(0, 20)))
    return {"pt": pt, "ecg": ecg, "ppg": ppg, "lead": [0 if finger else 5] * n}


def run(fx):
    s = pat.PatSession()
    for c in chunks(fx):
        s.add_chunk(c, now=1000.0)
    return s.analyse(now=1000.5)


class PatTests(unittest.TestCase):
    def test_synthetic_pat_is_recovered(self):
        out = run(synthetic(pat_ms=210))
        self.assertEqual(out["note"], "ok", out["note"])
        self.assertAlmostEqual(out["pat_ms"], 210, delta=30)
        self.assertAlmostEqual(out["hr"], 75, delta=3)

    def test_longer_delay_reads_longer(self):
        a, b = run(synthetic(pat_ms=180))["pat_ms"], run(synthetic(pat_ms=260))["pat_ms"]
        self.assertGreater(b - a, 50)

    def test_no_finger_gives_no_pat(self):
        out = run(synthetic(finger=False))
        self.assertIsNone(out["pat_ms"])
        self.assertFalse(out["finger"])

    def test_real_recording_gives_steady_pat(self):
        fx = json.loads(SAMPLE.read_text())
        out = run(fx)
        self.assertEqual(out["note"], "ok", out["note"])
        self.assertTrue(70 <= out["hr"] <= 90, out["hr"])
        self.assertTrue(pat.PAT_RANGE_MS[0] < out["pat_ms"] < pat.PAT_RANGE_MS[1], out["pat_ms"])
        self.assertLess(out["pat_spread_ms"], 30)

    def test_baseline_and_delta(self):
        fx = synthetic(seconds=30, pat_ms=200)
        s = pat.PatSession()
        for c in chunks(fx):
            s.add_chunk(c, now=1.0)
        first = s.analyse(now=1.2)
        self.assertIsNotNone(first["baseline_ms"])
        self.assertAlmostEqual(first["delta_ms"], 0, delta=15)

    def test_validation(self):
        good = next(chunks(synthetic(seconds=2)))
        self.assertEqual(pat.validate_chunk(good)[1], [])
        for bad in ({}, {**good, "ecg": good["ecg"][:-1]}, {**good, "pt": [5, 5] + good["pt"][2:]},
                    {**good, "lead": ["a"] * len(good["lead"])}, {**good, "ppg": [True] * len(good["ppg"])}, [1, 2]):
            self.assertTrue(pat.validate_chunk(bad)[1], bad)

    def test_idle_session_reports_nothing(self):
        out = pat.PatSession().analyse(now=5.0)
        self.assertFalse(out["active"])
        self.assertIsNone(out["pat_ms"])


if __name__ == "__main__":
    unittest.main()
