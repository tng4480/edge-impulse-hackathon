"""Send synthetic Wear OS packets to the real /vitals handler once a second."""

import argparse
import json
import math
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from run_sim import SCENARIO_HEADER, SCENARIOS, drift_fraction, sim_port, walking


def packet(scenario, elapsed):
    hr, spo2, skin = 72.0, 98.0, 33.1
    if scenario == "sepsis_drift":
        drift = drift_fraction(elapsed)
        hr += 44 * drift
        spo2 -= 4 * drift
        skin += 0.5 * drift
    if scenario == "walking" and walking(elapsed, scenario):
        hr += 32
    hr += 1.3 * math.sin(elapsed / 5)
    t = time.time_ns() // 1_000_000
    return {
        "t": t,
        "hr": round(hr, 1),
        "spo2": round(spo2, 1),
        "skin_temp_c": round(skin, 1),
        "source": "watch",
        "spo2_t": t,
        "ambient_c": 21.6,
        "ibi_ms": [round(60000 / hr + 16 * math.sin(elapsed * 1.7))],
    }


def run_watch(url, scenario, disconnect_after=8, disconnect_seconds=20, *, stop=None):
    wait = stop.wait if stop is not None else time.sleep
    endpoint = url.rstrip("/") + "/vitals"
    started = time.monotonic()
    next_send = started
    paused = False
    print(f"[watch] {scenario} -> {endpoint}", flush=True)
    while not wait(max(0, next_send - time.monotonic())):
        elapsed = time.monotonic() - started
        if scenario == "disconnect" and not paused and elapsed >= disconnect_after:
            paused = True
            print(f"[watch] Pausing sends for {disconnect_seconds:g} s", flush=True)
            if wait(disconnect_seconds):
                break
            elapsed = time.monotonic() - started
            print("[watch] Resuming sends", flush=True)
        req = Request(endpoint, json.dumps(packet(scenario, elapsed)).encode(),
                      {"Content-Type": "application/json", SCENARIO_HEADER: scenario})
        try:
            with urlopen(req, timeout=2) as response:
                response.read()
        except (URLError, TimeoutError) as exc:
            print(f"[watch] POST /vitals failed: {exc}", flush=True)
        next_send = started + math.floor(time.monotonic() - started) + 1


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be a positive number of seconds")
    return seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="board URL (defaults to localhost using SIM_PORT or 8000)")
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--disconnect-after", type=positive_seconds, default=8)
    parser.add_argument("--disconnect-seconds", type=positive_seconds, default=20)
    args = parser.parse_args()
    try:
        run_watch(args.url or f"http://127.0.0.1:{sim_port()}", args.scenario,
                  args.disconnect_after, args.disconnect_seconds)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
