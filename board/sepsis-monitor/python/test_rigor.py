"""Synthetic checks for rigor.py. Run: python test_rigor.py   (pure Python, no numpy)."""
import math
import random
import unittest

import rigor

FS = rigor.FS


def make(seconds, parts, noise=0.002, seed=1):
    """parts: list of (freq_hz, amp_g[, harmonics]). Returns ax, ay, az with gravity on z."""
    rnd = random.Random(seed)
    n = int(seconds * FS)
    ax, ay, az = [], [], []
    for i in range(n):
        t = i / FS
        s = 0.0
        for p in parts:
            f, a = p[0], p[1]
            harm = p[2] if len(p) > 2 else 1
            for h in range(1, harm + 1):
                s += a / h ** 2 * math.sin(2 * math.pi * f * h * t + h)
        ax.append(rnd.gauss(0, noise))
        ay.append(rnd.gauss(0, noise))
        az.append(1.0 + s + rnd.gauss(0, noise))
    return ax, ay, az


def run(sig, seconds):
    ax, ay, az = sig
    d, out = rigor.RigorDetector(), None
    for sec in range(int(WIN := rigor.WIN_S), int(seconds) + 1):
        k = int(sec * FS)
        out = d.update(float(sec), ax[:k], ay[:k], az[:k])
    return out


class RigorTests(unittest.TestCase):
    def test_still_with_breathing_is_quiet(self):
        self.assertFalse(run(make(40, [(0.25, 0.01)]), 40)["shaking"])

    def test_walking_is_not_shaking(self):
        # 2 Hz stride with strong harmonics (heel strikes), 0.15 g
        self.assertFalse(run(make(40, [(2.0, 0.15, 4)]), 40)["shaking"])

    def test_fast_walking_and_jogging_are_not_shaking(self):
        self.assertFalse(run(make(40, [(2.6, 0.3, 3)]), 40)["shaking"])

    def test_shivering_5hz_is_detected(self):
        out = run(make(40, [(5.0, 0.04), (0.25, 0.01)]), 40)
        self.assertTrue(out["shaking"], out)
        self.assertIsNotNone(out["since"])

    def test_shivering_with_breathing_and_small_sway(self):
        self.assertTrue(run(make(40, [(6.0, 0.03), (0.3, 0.015), (1.0, 0.01)]), 40)["shaking"])

    def test_single_short_burst_does_not_latch(self):
        quiet = make(30, [(0.25, 0.01)])
        burst = make(3, [(5.0, 0.05)], seed=2)
        ax = quiet[0] + burst[0] + quiet[0][:100]
        ay = quiet[1] + burst[1] + quiet[1][:100]
        az = quiet[2] + burst[2] + quiet[2][:100]
        self.assertFalse(run((ax, ay, az), len(ax) / FS - 1)["shaking"])

    def test_turns_off_after_it_stops(self):
        shake = make(25, [(5.0, 0.04)])
        quiet = make(25, [(0.25, 0.01)], seed=3)
        sig = tuple(a + b for a, b in zip(shake, quiet))
        self.assertTrue(run(sig, 25)["shaking"])
        self.assertFalse(run(sig, 50)["shaking"])

    def test_sensor_noise_alone_is_quiet(self):
        self.assertFalse(run(make(40, [], noise=0.005), 40)["shaking"])

    def test_warming_up_reports_reason(self):
        ax, ay, az = make(2, [(5.0, 0.04)])
        self.assertEqual(rigor.RigorDetector().update(0.0, ax, ay, az)["reason"], "warming up")


if __name__ == "__main__":
    unittest.main()
