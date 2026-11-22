"""Score held-out spoken digit sequences with the digit .eim (run on the board).

  python3 attention_selftest.py model/digits.eim sequences.npz
"""
import sys
import time

import numpy as np

from attention import decode
from model_runner import EimRunner

runner = EimRunner(sys.argv[1])
data = np.load(sys.argv[2], allow_pickle=True)
exact, digit_hits, total, t_used = 0, 0, 0, 0.0
for audio, exp in zip(data["audio"], data["expected"]):
    t0 = time.time()
    heard, _ = decode(audio.astype(np.float32), runner.classify)
    t_used += time.time() - t0
    exp = [int(d) for d in exp]
    exact += heard == exp
    digit_hits += sum(a == b for a, b in zip(heard, exp)) if len(heard) == len(exp) else 0
    total += 1
    if heard != exp:
        print("expected", exp, "heard", heard)
if total:
  print(f"sequences exactly right: {exact}/{total} = {exact / total:.0%}")
  print(f"digits right (when count matched): {digit_hits}/{4 * total}")
  print(f"mean decode time per recording: {t_used / total:.2f} s")

if "clips" in data:
    import collections
    hits, conf = 0, collections.Counter()
    for x, lab in zip(data["clips"], data["clip_labels"]):
        p = runner.classify(x.astype(np.float32))
        top = max(p, key=p.get)
        hits += top == lab
        if top != lab:
            conf[(str(lab), top)] += 1
    n = len(data["clip_labels"])
    print(f"single 1 s clips right: {hits}/{n} = {hits / n:.0%}")
    print("most common confusions:", conf.most_common(6))
runner.close()
