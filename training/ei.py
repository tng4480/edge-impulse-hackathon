"""Tiny Edge Impulse REST helper. The API key is read from a file path in EI_KEY_FILE."""
import json, os, urllib.error, urllib.request

PID = 1169195
BASE = f"https://studio.edgeimpulse.com/v1/api/{PID}/"
_key = open(os.environ["EI_KEY_FILE"]).read().strip()


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"x-api-key": _key, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return {"success": False, "http": e.code, "error": e.read().decode()[:600]}


def wait(job_id, every=5, limit=1500):
    import time
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            s = call("GET", f"jobs/{job_id}/status")
        except Exception:
            time.sleep(every)
            continue
        job = s.get("job", {})
        if job.get("finished"):
            return job
        time.sleep(every)
    return {"timeout": True}
