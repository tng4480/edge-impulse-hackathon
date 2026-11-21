"""Chest-motion gate: second Edge Impulse model (separate EI project, its key in EI_MOTION_KEY_FILE).

Classes: still, moving, shiver (acted "shiver-like motion"; label it that way in the pitch).

  python training/motion.py record still 60 --board 10.136.49.240   # wear the board, do the activity
  python training/motion.py setup        # create the impulse (4 s windows, Spectral Analysis, classifier)
  python training/motion.py train        # generate features, train, test, build the aarch64 .eim

`record` pulls GET /api/imu/raw?seconds=N from the board app (25 Hz, [[x, y, z] in g]), cuts it
into 10 s samples, and uploads them to training, or to testing with --test. Record one extra
session per class with --test, so test windows never come from a training session.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

OUT = pathlib.Path(__file__).parent / "out" / "motion"
FS = 25
SAMPLE_S = 10


def ei_call(method, path, body=None, key=None):
    key = key or open(os.environ["EI_MOTION_KEY_FILE"]).read().strip()
    pid = project_id(key)
    req = urllib.request.Request(f"https://studio.edgeimpulse.com/v1/api/{pid}/{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"x-api-key": key, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


_pid = {}


def project_id(key):
    if key not in _pid:
        req = urllib.request.Request("https://studio.edgeimpulse.com/v1/api/projects", headers={"x-api-key": key})
        _pid[key] = json.load(urllib.request.urlopen(req))["projects"][0]["id"]
    return _pid[key]


def wait(job_id):
    while True:
        try:
            j = ei_call("GET", f"jobs/{job_id}/status")["job"]
            if j.get("finished"):
                if not j.get("finishedSuccessful"):
                    sys.exit(f"job {job_id} failed")
                return
        except Exception:
            pass
        time.sleep(5)


def record(label, seconds, board, test=False):
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Recording '{label}' for {seconds} s. Start now.", flush=True)
    time.sleep(seconds)
    data = json.load(urllib.request.urlopen(f"http://{board}:8000/api/imu/raw?seconds={seconds}"))
    samples = data["samples"] if isinstance(data, dict) else data
    session = time.strftime("%H%M%S")
    category = "testing" if test else "training"
    n = SAMPLE_S * FS
    files = []
    for k in range(0, len(samples) - n + 1, n):
        chunk = samples[k:k + n]
        f = OUT / f"{label}.{session}_{k // n}.csv"
        with open(f, "w") as fh:
            fh.write("timestamp,accX,accY,accZ\n")
            for i, (x, y, z) in enumerate(chunk):
                fh.write(f"{i * 1000 // FS},{x:.4f},{y:.4f},{z:.4f}\n")
        files.append(str(f))
    print(f"{len(samples)} samples -> {len(files)} x {SAMPLE_S}s files, category {category}")
    key = open(os.environ["EI_MOTION_KEY_FILE"]).read().strip()
    subprocess.run(["edge-impulse-uploader", "--api-key", key, "--category", category, *files], check=False, shell=os.name == "nt")


def setup():
    imps = ei_call("GET", "impulses")["impulses"]
    iid = imps[0]["id"] if imps else ei_call("POST", "impulse/new", {"name": "Chest motion gate"})["id"]
    b = [ei_call("POST", f"impulse/get-new-block-id?impulseId={iid}", {})["blockId"] for _ in range(3)]
    body = {
        "inputBlocks": [{"id": b[0], "type": "time-series", "name": "Time series", "title": "Chest IMU 25 Hz",
                         "windowSizeMs": 4000, "windowIncreaseMs": 500, "frequencyHz": FS, "padZeros": False}],
        "dspBlocks": [{"id": b[1], "type": "spectral-analysis", "name": "Spectral features", "title": "Spectral Analysis",
                       "axes": ["accX", "accY", "accZ"], "input": b[0]}],
        "learnBlocks": [{"id": b[2], "type": "keras", "name": "Motion classifier", "title": "Classification", "dsp": [b[1]]}],
    }
    print(ei_call("POST", f"impulse?impulseId={iid}", body))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "impulse.json").write_text(json.dumps({"impulse": iid, "dsp": b[1], "learn": b[2]}))
    print("impulse", iid)


def train():
    cfg = json.loads((OUT / "impulse.json").read_text())
    iid, dsp, learn = cfg["impulse"], cfg["dsp"], cfg["learn"]
    r = ei_call("POST", f"jobs/generate-features?impulseId={iid}", {"dspId": dsp, "calculateFeatureImportance": True})
    wait(r["id"])
    r = ei_call("POST", f"jobs/train/keras/{learn}?impulseId={iid}", {"mode": "visual", "trainingCycles": 60})
    wait(r["id"])
    m = ei_call("GET", f"training/keras/{learn}/metadata?impulseId={iid}")
    for v in m.get("modelValidationMetrics", []):
        print(v.get("type"), "acc", round(v.get("accuracy", 0), 3), "confusion", v.get("confusionMatrix"))
    r = ei_call("POST", f"jobs/evaluate?impulseId={iid}", {"impulseId": iid, "evaluationType": "testing"})
    wait(r["id"])
    b = ei_call("POST", f"jobs/build-ondevice-model?type=runner-linux-aarch64&impulseId={iid}",
                {"engine": "tflite", "modelType": "int8"})
    wait(b["id"])
    key = open(os.environ["EI_MOTION_KEY_FILE"]).read().strip()
    url = (f"https://studio.edgeimpulse.com/v1/api/{project_id(key)}/deployment/download"
           f"?type=runner-linux-aarch64&modelType=int8&impulseId={iid}")
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"x-api-key": key})).read()
    (OUT / "motion.eim").write_bytes(data)
    print("motion.eim", len(data), "bytes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "setup", "train"])
    ap.add_argument("label", nargs="?")
    ap.add_argument("seconds", nargs="?", type=int, default=60)
    ap.add_argument("--board", default="10.136.49.240")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    {"record": lambda: record(a.label, a.seconds, a.board, a.test), "setup": setup, "train": train}[a.cmd]()
