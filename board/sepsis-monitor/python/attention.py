"""Attention check: "say these digits backwards", scored by the Edge Impulse digit model.

The watch (or the dashboard) shows e.g. 7 2 9 4; the wearer says "four nine two seven".
Reciting a digit string backwards is a standard bedside attention test; inattention is the core
feature of delirium, and new confusion is a sepsis red flag (NEWS2 "C", qSOFA).
This is a prompt for a human to check on the person, not a diagnosis.

  check = AttentionCheck(model/digits.eim)
  ch = check.new_challenge()              # {"id", "digits": [7, 2, 9, 4]}
  check.score(ch["id"], samples, fs)      # samples: int16 list/array of the spoken answer
"""
import random
import time

import numpy as np

WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
FS = 16000
HOP = FS // 4           # classify a 1 s window every 250 ms
MIN_P = 0.6             # a window counts as a digit only above this probability
MIN_RUN = 2             # and only if the same digit wins at least 2 windows in a row


def decode(samples, classify):
    """Digit sequence in a recording. `classify(window_int16) -> {label: p}`.

    A spoken word spans several overlapping windows, so consecutive windows with the same
    confident digit are merged into one word; noise, unknown words or low confidence split words.
    Returns (digits, [(digit, t_start_s, t_end_s), ...]).
    """
    x = np.asarray(samples, dtype=np.float32)
    if len(x) < FS:
        x = np.pad(x, (0, FS - len(x)))
    labels = []
    for s in range(0, len(x) - FS + 1, HOP):
        p = classify(x[s:s + FS])
        best = max(p, key=p.get)
        labels.append(best if best in WORDS and p[best] >= MIN_P else None)
    words, run, start = [], None, 0
    for i, lab in enumerate(labels + [None]):
        if lab != run:
            if run is not None and i - start >= MIN_RUN:
                words.append((WORDS.index(run), start * HOP / FS, (i - 1) * HOP / FS + 1.0))
            run, start = lab, i
    return [w[0] for w in words], words


class AttentionCheck:
    def __init__(self, runner, length=4):
        self.runner = runner          # model_runner.EimRunner for digits.eim (or None)
        self.length = length
        self.pending = {}

    def new_challenge(self):
        digits = [random.randrange(10)]
        while len(digits) < self.length:            # no immediate repeats: easier to hear and to say
            d = random.randrange(10)
            if d != digits[-1]:
                digits.append(d)
        cid = f"{int(time.time() * 1000)}"
        self.pending = {cid: {"digits": digits, "t": time.time()}}
        return {"id": cid, "digits": digits, "prompt": "Say these numbers backwards"}

    def score(self, cid, samples, fs=FS):
        ch = self.pending.get(cid)
        if ch is None:
            return {"ok": False, "error": "unknown or expired challenge"}
        if self.runner is None:
            return {"ok": False, "error": "digit model not loaded"}
        x = np.asarray(samples, dtype=np.float32)
        if fs != FS:                                # simple linear resample; the watch should send 16 kHz
            n = int(len(x) * FS / fs)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
        heard, words = decode(x, self.runner.classify)
        expected = ch["digits"][::-1]
        correct = sum(1 for a, b in zip(heard, expected) if a == b)
        passed = heard == expected
        gaps = [b[1] - a[2] for a, b in zip(words, words[1:])]
        return {"ok": True, "expected": expected, "heard": heard, "passed": passed,
                "correct_in_order": correct, "of": len(expected),
                "first_word_s": round(words[0][1], 2) if words else None,
                "longest_pause_s": round(max(gaps), 2) if gaps else None,
                "note": "Prompt for a carer to check on the person; not a diagnosis."}
