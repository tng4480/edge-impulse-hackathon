"""Attention check (digits backwards): Edge Impulse keyword-spotting model for spoken digits.

Why digits: a slurred-speech classifier did not generalise (docs/research/speech.md). Reciting a
short digit string backwards is a standard bedside attention test, and spoken digits have a large
open dataset with thousands of speakers: Google Speech Commands v2 (CC BY 4.0), here from the
Opus-compressed HF mirror danjacobellis/speech_commands_v2 (330 MB instead of 2.3 GB).

Classes: zero..nine, unknown (other words), noise (background noise clips).
The official Speech Commands splits are speaker-disjoint, so EI's test set has no training speakers.

  python training/speech_kws.py prep      # decode, resample to 16 kHz, write 1 s WAVs
  python training/speech_kws.py upload    # upload to EI (train / test)
  python training/speech_kws.py setup     # impulse: 1 s window, MFCC, classifier
  python training/speech_kws.py train     # features, train, test, build aarch64 .eim
Key: EI_SPEECH_KEY_FILE (separate EI project).
"""
import argparse
import collections
import io
import json
import os
import pathlib
import random
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "speechcmd"
WAV = ROOT / "data" / "speechcmd_wav"
OUT = ROOT / "training" / "out" / "speech"
DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
PER_CLASS = {"training": 600, "testing": 120}
FS = 16000


def label_of(path):
    word = path.replace("\\", "/").split("/")[-2]
    if word in DIGITS:
        return word
    if word.startswith("_"):          # _background_noise_ / _silence_
        return "noise"
    return "unknown"


def speaker_of(path):
    return path.replace("\\", "/").split("/")[-1].split("_nohash_")[0]


def prep():
    import numpy as np
    import pandas as pd
    import soundfile as sf
    from scipy.signal import resample_poly
    random.seed(0)
    stats = {}
    for split, category in (("train", "training"), ("test", "testing")):
        df = pd.read_parquet(SRC / f"{split}-00000-of-00001.parquet")
        df["lab"] = df["path"].map(label_of)
        print(split, len(df), df["lab"].value_counts().to_dict(), flush=True)
        out = WAV / category
        out.mkdir(parents=True, exist_ok=True)
        counts = collections.Counter()
        for lab, g in df.groupby("lab"):
            rows = g.sample(n=min(PER_CLASS[category], len(g)), random_state=0)
            for _, r in rows.iterrows():
                x, sr = sf.read(io.BytesIO(r["opus"]["bytes"]), dtype="float32")
                if x.ndim > 1:
                    x = x.mean(axis=1)
                if sr != FS:
                    g_ = np.gcd(sr, FS)
                    x = resample_poly(x, FS // g_, sr // g_).astype("float32")
                if lab == "noise" and len(x) > FS:   # long noise file: take a random 1 s cut
                    s = random.randrange(0, len(x) - FS)
                    x = x[s:s + FS]
                x = np.pad(x[:FS], (0, max(0, FS - len(x))))
                name = f"{lab}.{speaker_of(r['path'])}_{counts[lab]}.wav"
                sf.write(out / name, x, FS, subtype="PCM_16")
                counts[lab] += 1
        # The Opus mirror has no _background_noise_ files, so make the noise class: white, pink and
        # brown noise, mains hum, and near-silence, at random levels.
        rng = np.random.default_rng(0 if category == "training" else 1)
        for i in range(PER_CLASS[category]):
            kind = rng.choice(["white", "pink", "brown", "hum", "quiet"])
            w = rng.standard_normal(FS)
            if kind == "pink":
                f = np.fft.rfftfreq(FS, 1 / FS); f[0] = 1
                w = np.fft.irfft(np.fft.rfft(w) / np.sqrt(f), FS)
            elif kind == "brown":
                w = np.cumsum(w); w -= w.mean()
            elif kind == "hum":
                t = np.arange(FS) / FS
                w = sum(np.sin(2 * np.pi * 50 * k * t + rng.uniform(0, 6)) / k for k in (1, 2, 3)) + 0.1 * w
            w = w / (np.abs(w).max() + 1e-9)
            level = 10 ** rng.uniform(-3.5 if kind == "quiet" else -2.5, -2.5 if kind == "quiet" else -0.7)
            sf.write(out / f"noise.synth_{i}.wav", (w * level).astype("float32"), FS, subtype="PCM_16")
            counts["noise"] += 1
        stats[category] = dict(counts)
        print(category, dict(counts), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prep.json").write_text(json.dumps(stats, indent=1))


def key():
    return open(os.environ["EI_SPEECH_KEY_FILE"]).read().strip()


_pid = {}


def project_id():
    k = key()
    if k not in _pid:
        req = urllib.request.Request("https://studio.edgeimpulse.com/v1/api/projects", headers={"x-api-key": k})
        _pid[k] = json.load(urllib.request.urlopen(req))["projects"][0]["id"]
    return _pid[k]


def ei_call(method, path, body=None):
    req = urllib.request.Request(f"https://studio.edgeimpulse.com/v1/api/{project_id()}/{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"x-api-key": key(), "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def wait(job_id):
    while True:
        try:
            j = ei_call("GET", f"jobs/{job_id}/status")["job"]
            if j.get("finished"):
                if not j.get("finishedSuccessful"):
                    sys.exit(f"job {job_id} failed")
                return
        except urllib.error.HTTPError:
            raise
        except Exception:
            pass
        time.sleep(5)


def upload():
    for category in ("training", "testing"):
        files = sorted(p.name for p in (WAV / category).glob("*.wav"))   # relative: Windows caps the command line
        print(category, len(files), "files", flush=True)
        for i in range(0, len(files), 150):
            subprocess.run(["edge-impulse-uploader", "--api-key", key(), "--category", category, *files[i:i + 150]],
                           check=True, shell=os.name == "nt", stdout=subprocess.DEVNULL, cwd=WAV / category)
            print(" uploaded", min(i + 150, len(files)), flush=True)


def setup():
    imps = ei_call("GET", "impulses")["impulses"]
    iid = imps[0]["id"] if imps else ei_call("POST", "impulse/new", {"name": "Digits attention check"})["id"]
    b = [ei_call("POST", f"impulse/get-new-block-id?impulseId={iid}", {})["blockId"] for _ in range(3)]
    body = {
        "inputBlocks": [{"id": b[0], "type": "time-series", "name": "Audio", "title": "Audio 16 kHz",
                         "windowSizeMs": 1000, "windowIncreaseMs": 500, "frequencyHz": FS, "padZeros": True}],
        "dspBlocks": [{"id": b[1], "type": "mfcc", "name": "MFCC", "title": "Audio (MFCC)",
                       "axes": ["audio"], "input": b[0], "implementationVersion": 4}],
        "learnBlocks": [{"id": b[2], "type": "keras", "name": "Digit classifier", "title": "Classification", "dsp": [b[1]]}],
    }
    print(ei_call("POST", f"impulse?impulseId={iid}", body))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "impulse.json").write_text(json.dumps({"impulse": iid, "dsp": b[1], "learn": b[2]}))
    print("impulse", iid)


def train(cycles):
    cfg = json.loads((OUT / "impulse.json").read_text())
    iid, dsp, learn = cfg["impulse"], cfg["dsp"], cfg["learn"]
    r = ei_call("POST", f"jobs/generate-features?impulseId={iid}", {"dspId": dsp})
    wait(r["id"])
    print("features done", flush=True)
    r = ei_call("POST", f"jobs/train/keras/{learn}?impulseId={iid}", {"mode": "visual", "trainingCycles": cycles})
    wait(r["id"])
    m = ei_call("GET", f"training/keras/{learn}/metadata?impulseId={iid}")
    for v in m.get("modelValidationMetrics", []):
        print(v.get("type"), "val acc", round(v.get("accuracy", 0), 3), flush=True)
    r = ei_call("POST", f"jobs/evaluate?impulseId={iid}", {"impulseId": iid, "evaluationType": "testing"})
    wait(r["id"])
    b = ei_call("POST", f"jobs/build-ondevice-model?type=runner-linux-aarch64&impulseId={iid}",
                {"engine": "tflite", "modelType": "int8"})
    wait(b["id"])
    url = (f"https://studio.edgeimpulse.com/v1/api/{project_id()}/deployment/download"
           f"?type=runner-linux-aarch64&modelType=int8&impulseId={iid}")
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"x-api-key": key()})).read()
    (OUT / "digits.eim").write_bytes(data)
    print("digits.eim", len(data), "bytes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "upload", "setup", "train"])
    ap.add_argument("--cycles", type=int, default=100)
    a = ap.parse_args()
    {"prep": prep, "upload": upload, "setup": setup, "train": lambda: train(a.cycles)}[a.cmd]()
