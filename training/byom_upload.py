"""Import the LightGBM sepsis model into Edge Impulse (Bring Your Own Model) as its OWN impulse,
then build and download a Linux aarch64 .eim for the UNO Q.

Never touches impulses 1 (keyword audio) or 2 (dense net): every call passes impulse_id.
Key: path in EI_KEY_FILE.  Usage: python training/byom_upload.py
"""
import json
import os
import pathlib
import sys
import time
import urllib.request

from edgeimpulse_api import ApiClient, Configuration, JobsApi, LearnApi
from edgeimpulse_api.models.save_pretrained_model_request import SavePretrainedModelRequest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ei  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "out"
PID = ei.PID
NAME = "Sepsis risk - LightGBM 24h trends (BYOM)"

key = open(os.environ["EI_KEY_FILE"]).read().strip()
cfg = Configuration(host="https://studio.edgeimpulse.com/v1")
cfg.api_key["ApiKeyAuthentication"] = key
client = ApiClient(cfg)
learn, jobs = LearnApi(client), JobsApi(client)


def wait(job_id):
    j = ei.wait(job_id, every=5, limit=1500)
    if not j.get("finishedSuccessful"):
        log = ei.call("GET", f"jobs/{job_id}/stdout")
        raise SystemExit(f"job {job_id} failed: {json.dumps(log)[:1500]}")
    return j


# 1. a dedicated impulse (Studio ignores the requested name, so reuse by id if given)
iid = int(os.environ["EI_IMPULSE_ID"]) if os.environ.get("EI_IMPULSE_ID") else ei.call("POST", "impulse/new", {"name": NAME})["id"]
print("impulse", iid)
assert iid not in (1, 2)

# 2. upload model + representative features
# ONNX of the LightGBM trees (see to_onnx.py): the free plan cannot build classical-ML (lgbm) models
r = learn.upload_pretrained_model(project_id=PID, model_file=str(OUT / "model_gemm.onnx"), model_file_name="model.onnx",
                                  model_file_type="onnx", impulse_id=iid)
print("upload job", r.id)
wait(r.id)

info = learn.get_pretrained_model_info(project_id=PID, impulse_id=iid)
print("available types", info.available_model_types, "outputs", info.model.outputs if info.model else None)

# 3. describe inputs/outputs: 32 raw features in, two classes out (order = LightGBM classes 0, 1)
req = SavePretrainedModelRequest.from_dict({
    "input": {"inputType": "other"},
    "model": {"modelType": "classification", "labels": ["healthy", "sepsis"]},
})
print(learn.save_pretrained_model_parameters(project_id=PID, save_pretrained_model_request=req, impulse_id=iid))

# 4. build the Linux aarch64 runner (.eim) and download it
mtype = "float32"
b = ei.call("POST", f"jobs/build-ondevice-model?type=runner-linux-aarch64&impulseId={iid}",
            {"engine": "tflite", "modelType": mtype})
print("build", b)
wait(b["id"])
req = urllib.request.Request(
    f"https://studio.edgeimpulse.com/v1/api/{PID}/deployment/download?type=runner-linux-aarch64&modelType={mtype}&impulseId={iid}",
    headers={"x-api-key": key})
data = urllib.request.urlopen(req).read()
dst = OUT / "sepsis-lgbm-aarch64.eim"
dst.write_bytes(data)
print("downloaded", dst, len(data), "bytes")
