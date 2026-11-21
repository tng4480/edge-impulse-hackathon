"""Feasibility check for a slurred-speech (dysarthria) screen on TORGO, before Edge Impulse.

Leave-one-speaker-out: every speaker is scored by a model that never heard them. This is the
only honest test, because voice and recording-setup cues let models recognise speakers.
Also checks the microphone confound (arrayMic vs headMic).
Data: Hugging Face abnerh/TORGO-database (TORGO, University of Toronto; research licence).
"""
import glob, io, json, pathlib, re
import numpy as np, pyarrow.parquet as pq, soundfile as sf, librosa, lightgbm as lgb
from sklearn.metrics import roc_auc_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 16000

def feats(y):
    m = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13)
    d = librosa.feature.delta(m)
    sc = librosa.feature.spectral_centroid(y=y, sr=SR)
    zc = librosa.feature.zero_crossing_rate(y)
    rms = librosa.feature.rms(y=y)
    voiced = float((rms > 0.3 * rms.max()).mean())
    return np.concatenate([m.mean(1), m.std(1), d.std(1), [sc.mean(), sc.std(), zc.mean(), rms.std() / (rms.mean() + 1e-9), voiced]])

rows = []
for f in sorted(glob.glob(str(ROOT / "data" / "torgo" / "*.parquet"))):
    t = pq.read_table(f, columns=["audio", "speech_status", "duration"]).to_pylist()
    for r in t:
        p = r["audio"]["path"]
        m = re.match(r"([A-Z]+\d+)_(\d+)_(\w+?Mic)_", p)
        if not m:
            continue
        y, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        if y.ndim > 1: y = y.mean(1)
        if sr != SR: y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        if len(y) < SR // 2: continue
        rows.append((m.group(1), m.group(3), r["speech_status"] == "dysarthria", feats(y)))
    print(f, len(rows), flush=True)

spk = np.array([r[0] for r in rows]); mic = np.array([r[1] for r in rows])
y = np.array([r[2] for r in rows]); X = np.stack([r[3] for r in rows])
print("speakers:", {s: (int((spk == s).sum()), bool(y[spk == s][0])) for s in sorted(set(spk))})
print("mics:", {m: int((mic == m).sum()) for m in set(mic)})
p = np.zeros(len(y))
for s in sorted(set(spk)):
    tr, te = spk != s, spk == s
    clf = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, class_weight="balanced", verbose=-1)
    clf.fit(X[tr], y[tr]); p[te] = clf.predict_proba(X[te])[:, 1]
print(f"clip-level AUC, leave-one-speaker-out: {roc_auc_score(y, p):.3f}")
res = {}
for s in sorted(set(spk)):
    te = spk == s
    res[s] = {"dysarthric": bool(y[te][0]), "clips": int(te.sum()), "mean_p": round(float(p[te].mean()), 3),
              "clips_called_dysarthric": round(float((p[te] > 0.5).mean()), 3)}
    print(s, res[s])
sp = sorted(set(spk))
print("speaker-level AUC (mean p per speaker):", roc_auc_score([res[s]["dysarthric"] for s in sp], [res[s]["mean_p"] for s in sp]))
for mname in set(mic):
    k = mic == mname
    if len(set(y[k])) == 2: print(f"AUC within {mname}: {roc_auc_score(y[k], p[k]):.3f}")
(ROOT / "training" / "out" / "speech_baseline.json").write_text(json.dumps(res, indent=1))
