"""Stand-in for the board's endpoint: POST /vitals, validates the JSON contract and prints each sample.

    python wearos/tools/test_server.py            # listens on 0.0.0.0:8000
    python wearos/tools/test_server.py --port 8001

Emulator: the app's default address 10.0.2.2:8000 reaches this server on the laptop.
Real watch: set the app's IP to this laptop's Wi-Fi IP (allow Python through Windows Firewall).
"""

import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYS = {"t", "hr", "spo2", "skin_temp_c", "source"}
# Optional keys (older builds omit them):
#   spo2_t    epoch ms the SpO2 spot reading was taken
#   ambient_c ambient temperature around the watch, °C (context only)
#   ibi_ms    valid (status 0) inter-beat intervals since the previous sample, ms
OPTIONAL_KEYS = {"spo2_t", "ambient_c", "ibi_ms"}


def is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def problems(body: object) -> list[str]:
    if not isinstance(body, dict):
        return ["body is not a JSON object"]
    errs = []
    missing = KEYS - set(body)
    unknown = set(body) - KEYS - OPTIONAL_KEYS
    if missing:
        errs.append(f"missing keys {sorted(missing)}")
    if unknown:
        errs.append(f"unknown keys {sorted(unknown)}")
    if not is_int(body.get("t")):
        errs.append("t must be an integer (epoch ms)")
    if "spo2_t" in body:
        spo2_t = body["spo2_t"]
        if spo2_t is not None and not is_int(spo2_t):
            errs.append("spo2_t must be an integer (epoch ms) or null")
        if (spo2_t is None) != (body.get("spo2") is None):
            errs.append("spo2_t must be null exactly when spo2 is null")
        if is_int(spo2_t) and is_int(body.get("t")) and spo2_t > body["t"]:
            errs.append("spo2_t is later than t")
    for key in ("hr", "spo2"):
        v = body.get(key)
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            errs.append(f"{key} must be a number or null")
    for key in ("skin_temp_c", "ambient_c"):
        v = body.get(key)
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            errs.append(f"{key} must be a number or null")
    ibi = body.get("ibi_ms")
    if ibi is not None and (not isinstance(ibi, list) or not ibi or not all(is_int(x) and x > 0 for x in ibi)):
        errs.append("ibi_ms must be a non-empty list of positive integers, or null")
    if body.get("source") != "watch":
        errs.append('source must be "watch"')
    return errs


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/vitals":
            self.send_error(404)
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
        errs = problems(body) if body is not None else ["invalid JSON"]
        now = datetime.now().strftime("%H:%M:%S")
        if errs:
            print(f"{now} {self.client_address[0]} REJECTED {raw!r}: {'; '.join(errs)}", flush=True)
            self._reply(400, {"ok": False, "errors": errs})
            return
        lag_s = datetime.now().timestamp() - body["t"] / 1000
        spo2_age = ""
        if body.get("spo2_t") is not None:
            spo2_age = f" (taken {(body['t'] - body['spo2_t']) / 1000:.0f}s before t)"
        print(
            f"{now} {self.client_address[0]} hr={body['hr']} spo2={body['spo2']}{spo2_age} "
            f"skin={body['skin_temp_c']} ambient={body.get('ambient_c')} "
            f"ibi={len(body.get('ibi_ms') or [])} (sample age {lag_s:.1f}s)",
            flush=True,
        )
        self._reply(200, {"ok": True})

    def _reply(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # quiet default access log; we print our own line
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Listening on http://{args.host}:{args.port}/vitals", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
