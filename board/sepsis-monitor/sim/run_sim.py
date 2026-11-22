"""Run the board app on localhost with a synthetic STM32 Bridge."""

import importlib
import math
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import types
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "python"
SCENARIOS = ("normal", "sepsis_drift", "disconnect", "walking", "shivering")
SCENARIO_HEADER = "X-Sim-Scenario"
DRIFT_SECONDS = 240
FS = 25


def drift_fraction(seconds):
    return min(seconds / DRIFT_SECONDS, 1.0)


def walking(seconds, scenario):
    first_walk = 35 if scenario == "walking" else 75
    return seconds >= first_walk and (seconds - first_walk) % 90 < 12


class Bridge:
    def __init__(self, scenario):
        self.scenario = scenario
        self.requested_scenario = scenario
        self.scenario_start = 0
        self.sample = 0
        self.breath_phase = 0.0
        self.noise = random.Random(25)

    def call(self, name, *args):
        if name == "drain":
            return self.drain()
        if name == "env":
            seconds = self.sample / FS
            return f"{21.6 + 0.2 * math.sin(seconds / 60):.2f},46.0,320,80"
        if name == "status":
            return "imu=1 thermo=1 light=1 vibro=1"
        if name == "vibe":
            ms, power = args
            print(f"[sim] Vibro {ms} ms at power {power}", flush=True)
            return 1
        raise ValueError(f"unknown Bridge call {name!r}")

    def drain(self):
        start = self.sample
        scenario = self.requested_scenario
        if scenario != self.scenario:
            self.scenario = scenario
            self.scenario_start = start
        rows = []
        for i in range(start, start + FS):
            seconds = (i - self.scenario_start) / FS
            rr = 15
            if scenario == "sepsis_drift":
                rr += 15 * drift_fraction(seconds)
            self.breath_phase += math.tau * rr / (60 * FS)
            breath = math.sin(self.breath_phase)
            step = 0
            if scenario != "sepsis_drift" and walking(seconds, scenario):
                step = math.sin(math.tau * 1.8 * seconds)
            shake = 0.0
            if scenario == "shivering" and 20 <= seconds % 80 < 55:   # 35 s of chills, then rest
                shake = math.sin(math.tau * 5.5 * seconds)
            axes = (60 + 11 * breath + 70 * step + 25 * shake, -30 + 4 * breath, 997 + 7 * breath + 210 * step + 35 * shake)
            rows.append(",".join(str(round(a + self.noise.gauss(0, 1))) for a in axes))
        self.sample += FS
        return f"{40 * start},{40 * (self.sample - 1)}|" + ";".join(rows)


class App:
    def __init__(self):
        self.stop = threading.Event()
        self.worker = None

    def run(self, user_loop):
        def run_loop():
            while not self.stop.is_set():
                user_loop()

        self.worker = threading.Thread(target=run_loop, name="sim-board-loop", daemon=True)
        self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker is not None:
            self.worker.join()


def sim_port():
    raw = os.environ.get("SIM_PORT", "8000")
    try:
        port = int(raw)
        if 0 <= port <= 65535:
            return port
    except ValueError:
        pass
    raise ValueError("SIM_PORT must be an integer from 0 to 65535 (0 picks a free port)")


@contextmanager
def serve_sim(port, scenario="normal"):
    """Import the actual app and give it a private working tree and loopback listener."""
    app = App()
    arduino = types.ModuleType("arduino")
    arduino.__path__ = []
    arduino.app_utils = types.ModuleType("arduino.app_utils")
    arduino.app_utils.App = app
    bridge = Bridge(scenario)
    arduino.app_utils.Bridge = bridge

    servers = Queue()

    def bind_loopback(_address, handler):
        class SimHandler(handler):
            def do_POST(self):
                super().do_POST()
                # The extra header synchronizes the simulated IMU with the watch's scenario.
                scenario = self.headers.get(SCENARIO_HEADER)
                if self.path == "/vitals" and scenario in SCENARIOS:
                    bridge.requested_scenario = scenario

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), SimHandler)
        except OSError as exc:
            servers.put(exc)
            raise
        servers.put(server)
        return server

    with tempfile.TemporaryDirectory(prefix="sepsis-sim-") as work_dir:
        # Keep the demo's SQLite, profile and baseline away from the board's data.
        staged = Path(work_dir) / "python"
        shutil.copytree(APP_DIR, staged, ignore=shutil.ignore_patterns(
            "data", "baseline.json", "__pycache__", "*.eim",
        ))
        with patch.dict(sys.modules, {"arduino": arduino, "arduino.app_utils": arduino.app_utils}):
            sys.path.insert(0, str(staged))
            server = None
            main = None
            try:
                # main starts its own HTTP thread at import. Keep its handler and routing intact.
                with patch("http.server.ThreadingHTTPServer", bind_loopback):
                    main = importlib.import_module("main")
                    bound = servers.get(timeout=10)
                if isinstance(bound, OSError):
                    raise bound
                server = bound
                yield f"http://127.0.0.1:{server.server_port}"
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                app.close()
                if main is not None:
                    main.handoff.close()
                sys.path.remove(str(staged))


def main():
    scenario = os.environ.get("SIM_SCENARIO", "normal")
    if scenario not in SCENARIOS:
        raise ValueError(f"SIM_SCENARIO must be one of {', '.join(SCENARIOS)}")
    try:
        with serve_sim(sim_port(), scenario) as url:
            print(f"[sim] {url}  ({scenario})", flush=True)
            while True:
                time.sleep(1)  # Ctrl+C can interrupt sleep on Windows Python 3.12.
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
