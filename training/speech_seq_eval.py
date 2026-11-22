"""Make spoken digit-sequence test recordings from held-out speakers (the EI test set speakers).

Each recording: one speaker, 4 different digits, 0.15-0.7 s pauses, 0.5 s lead-in, light noise.
Writes data/speechcmd_wav/sequences.npz (int16 audio + expected digits), which
board/sepsis-monitor/python/attention_selftest.py scores with the real .eim on the board.
"""
import collections
import pathlib
import random

import numpy as np
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST = ROOT / "data" / "speechcmd_wav" / "testing"
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
FS = 16000


def trim(x, thr=0.02):
    """Cut a 1 s clip down to the spoken part (plus 50 ms each side)."""
    e = np.convolve(np.abs(x), np.ones(400) / 400, mode="same")
    idx = np.where(e > thr * np.abs(x).max())[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - 800): idx[-1] + 800]


def main(n=60, seed=0):
    rng = random.Random(seed)
    by_spk = collections.defaultdict(dict)
    for p in TEST.glob("*.wav"):
        lab, rest = p.stem.split(".", 1)
        if lab in WORDS:
            by_spk[rest.rsplit("_", 1)[0]].setdefault(WORDS.index(lab), p)
    speakers = [s for s, d in by_spk.items() if len(d) >= 4]
    print(len(speakers), "held-out speakers with 4+ different digits")
    audio, expected = [], []
    for i in range(n):
        spk = rng.choice(speakers)
        digits = rng.sample(sorted(by_spk[spk]), 4)
        parts = [np.zeros(int(0.5 * FS), np.float32)]
        for d in digits:
            x, _ = sf.read(by_spk[spk][d], dtype="float32")
            parts += [trim(x), np.zeros(int(rng.uniform(0.15, 0.7) * FS), np.float32)]
        y = np.concatenate(parts + [np.zeros(int(0.5 * FS), np.float32)])
        y += np.random.default_rng(i).standard_normal(len(y)).astype(np.float32) * 0.003
        audio.append((np.clip(y, -1, 1) * 32767).astype(np.int16))
        expected.append(digits)
    # Single-word test: 50 held-out clips per class (digits, unknown, noise).
    clips, clip_labels = [], []
    per = collections.defaultdict(list)
    for p in sorted(TEST.glob("*.wav")):
        per[p.stem.split(".", 1)[0]].append(p)
    for lab, ps in sorted(per.items()):
        for p in rng.sample(ps, min(50, len(ps))):
            x, _ = sf.read(p, dtype="int16")
            clips.append(x)
            clip_labels.append(lab)
    np.savez(ROOT / "data" / "speechcmd_wav" / "sequences.npz",
             audio=np.array(audio, dtype=object), expected=np.array(expected),
             clips=np.array(clips), clip_labels=np.array(clip_labels))
    print("wrote", n, "sequences")


if __name__ == "__main__":
    main()
