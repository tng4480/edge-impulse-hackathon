"""Start an isolated simulator and exercise the board routes over HTTP."""

import json
import re
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fake_watch import run_watch
from run_sim import serve_sim


HEALTHY = "p000147"
SEPSIS = "p112060"
# At 0.4 the fixture's alert window barely covers two ticks plus the five-second escalation.
SECONDS_PER_HOUR = 0.48


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_for(description, read, timeout, interval=0.1):
    deadline = time.monotonic() + timeout
    while True:
        value = read()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {description}")
        time.sleep(interval)


class Rehearsal:
    def __init__(self, url):
        self.url = url
        self.failed = 0

    def step(self, title, action, *args):
        try:
            result = action(*args)
        except Exception as exc:
            self.failed += 1
            print(f"FAIL {title} ({exc})", flush=True)
            return None
        print(f"PASS {title}", flush=True)
        return result

    def request(self, path, body=None, *, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.url + path, data, {"Content-Type": "application/json"}, method=method)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, response.headers.get_content_type(), response.read()
        except HTTPError as exc:
            with exc:
                raise AssertionError(f"{req.get_method()} {path} returned {exc.code}: "
                                     f"{exc.read(300).decode(errors='replace')}") from exc

    def api(self, path, body=None):
        status, kind, data = self.request(path, body)
        require(status == 200 and kind == "application/json", f"{path}: {status} {kind}")
        result = json.loads(data)
        require(result.get("ok", True), f"{path}: {result}")
        return result

    def pages(self, *paths):
        for path in paths:
            status, kind, data = self.request(path)
            require(status == 200 and kind == "text/html" and b"<html" in data.lower(),
                    f"{path} did not return HTML")

    def controls(self):
        require(self.request("/vitals", method="OPTIONS")[0] == 204, "watch preflight failed")
        self.api("/vibe", {})
        self.api("/override", {"rr": 16})
        try:
            require(self.api("/api/state")["vitals"]["rr"]["v"] == 16, "RR override did not apply")
        finally:
            self.api("/override", {"rr": None})
        self.api("/fault", {"kind": "internet_cut", "seconds": 30})
        try:
            require(self.api("/api/state")["links"]["net"]["simulated"], "network fault did not apply")
        finally:
            self.api("/fault", {"kind": "internet_cut", "clear": True})
        require(not self.api("/api/state")["links"]["net"]["simulated"], "network fault did not clear")

    def sensors(self):
        def ready():
            status = self.api("/api/state")
            return status["env"]["temp_c"] is not None and status["imu_hz"] == 25

        wait_for("environment reading and 25 Hz IMU", ready, 5)
        raw = self.api("/api/imu/raw?seconds=1")
        require(raw["fs"] == 25 and raw["n"] == 25 and all(len(row) == 3 for row in raw["samples"]),
                "unexpected IMU samples")
        require(self.api("/api/state")["devices"] == "imu=1 thermo=1 light=1 vibro=1",
                "incomplete device status")

    def stop_replay(self):
        self.api("/replay/stop", {})
        require(not self.api("/api/replay")["active"], "replay still active")
        wait_for("live alert to clear", lambda: not self.api("/api/state")["alert"]["active"], 3)

    def healthy(self):
        before = {t["id"] for t in self.api("/api/handoff?all=1")["tasks"]}
        self.api("/replay/start", {"case": HEALTHY, "seconds_per_hour": 0.4})

        def finished():
            replay = self.api("/api/replay")
            require(replay["case"] == HEALTHY, "wrong healthy replay case")
            require(not self.api("/api/state")["alert"]["active"], "healthy replay activated a board alert")
            if replay["done"]:
                require(any(row["risk"] is not None for row in replay["timeline"]), "model never scored")
                require(not any(row["alert"] for row in replay["timeline"]), "healthy timeline contains a model alert")
                return True

        try:
            wait_for("healthy replay to finish", finished, 22, interval=0.25)
            new_tasks = [t for t in self.api("/api/handoff?all=1")["tasks"] if t["id"] not in before]
            require(not new_tasks, "healthy replay opened a task")
        finally:
            self.stop_replay()

    def sepsis_alert(self):
        require(self.api("/escalation", {"seconds": 5})["after_s"] == 5, "escalation timer did not apply")
        self.api("/replay/start", {"case": SEPSIS, "seconds_per_hour": SECONDS_PER_HOUR})

        def model_alerted():
            replay = self.api("/api/replay")
            return (replay["case"] == SEPSIS and replay["risk"]["alert"]
                    and self.api("/api/state")["alert"]["active"])

        wait_for("a p112060 model alert and board alert", model_alerted, 10)

    def escalation(self):
        def escalated():
            escalation = self.api("/api/state")["escalation"]
            if escalation["active"]:
                require(escalation["replay"] and escalation["sbar"]["assessment"], "missing replay SBAR")
                return True

        wait_for("active replay escalation", escalated, 8, interval=0.05)

    def alert_task(self):
        def find():
            for task in self.api("/api/handoff")["tasks"]:
                if (task["source"] == "model" and task["kind"] == "alert" and task["status"] == "pending"
                        and task["replay"] and task["snapshot"]["replay"]["case"] == SEPSIS):
                    return task["id"]

        return wait_for("a pending p112060 handoff task", find, 2)

    def accept(self, task_id):
        require(task_id, "p112060 handoff task missing")
        task = self.api(f"/api/handoff/{task_id}/accept", {"nurse": "Demo Nurse"})["task"]
        require(task["status"] == "accepted" and task["accepted_by"] == "Demo Nurse" and task["accepted_at"],
                "named nurse acceptance missing")

    def resolve(self, task_id):
        require(task_id, "p112060 handoff task missing")
        body = {"action": "Rehearsal review completed", "outcome": "no_action"}
        task = self.api(f"/api/handoff/{task_id}/resolve", body)["task"]
        require(task["status"] == "resolved" and task["resolved_at"]
                and all(task[k] == v for k, v in body.items()), "resolution was not recorded")

    def ack(self, task_id):
        require(task_id, "p112060 handoff task missing")
        task = self.api("/ack", {})["task"]
        require(task and task["id"] == task_id and task["wearer_ack_at"], "acknowledgement was not recorded")
        state = self.api("/api/state")
        require(state["handoff_receipt"]["task_id"] == task_id and state["alert"]["muted"],
                "wearer receipt or mute missing")

    def check_in(self):
        result = self.api("/api/checkin", {"feel_unwell": True, "by": "wearer"})
        require(len(result["tasks"]) == 1, "expected one concern task")
        task = result["tasks"][0]
        require(task["source"] == "wearer" and task["kind"] == "concern"
                and task["status"] == "pending" and not task["replay"], "missing live wearer concern")
        require(any(t["id"] == task["id"] for t in self.api("/api/handoff")["tasks"]),
                "nurse queue missed the wearer concern")

    def fhir(self, task_id):
        require(task_id, "p112060 handoff task missing")
        bundle = self.api(f"/api/fhir/{task_id}")
        require(bundle["resourceType"] == "Bundle" and bundle["type"] == "collection", "expected FHIR Bundle")
        refs = {e["fullUrl"] for e in bundle["entry"]}
        resources = [e["resource"] for e in bundle["entry"]]
        task = next((r for r in resources if r["resourceType"] == "Task"), {})
        require(task.get("status") == "completed" and task["identifier"][0]["value"] == task_id
                and sum(r["resourceType"] == "Observation" for r in resources) == 5
                and any(r["resourceType"] == "Provenance" for r in resources), "incomplete FHIR resources")
        require(all(i["valueReference"]["reference"] in refs for i in task["input"] if "valueReference" in i),
                "unresolved FHIR reference")
        qr = self.api(f"/api/fhir/{task_id}/qr")
        require(qr["chars"] == len(qr["payload"])
                and (qr["payload"].startswith("SEPSISFHIR:") if qr["inline"]
                     else qr["payload"] == f"{self.url}/api/fhir/{task_id}"), "invalid FHIR QR payload")

    def stress(self):
        self.pages("/stress", "/stress.html")
        catalogue = self.api("/api/stress")
        require(any(c["id"] == SEPSIS for c in catalogue["cases"]) and catalogue["scenarios"],
                "empty stress catalogue")
        baseline = self.api(f"/api/stress?case={SEPSIS}&scenario=baseline")
        require(baseline["case"] == SEPSIS and any(t["model_alert"] for t in baseline["timeline"]),
                "stress lab did not score the replay")
        require(bool(self.api("/api/stress/summary")), "empty stress summary")

    def watch_disconnect(self):
        done = threading.Event()
        watch = threading.Thread(target=run_watch, args=(self.url, "disconnect", 3, 18),
                                 kwargs={"stop": done}, daemon=True)
        watch.start()
        try:
            def fresh():
                state = self.api("/api/state")
                return state["links"]["watch"]["state"] == "connected" and state["vitals"]["hr"]["src"] == "watch"

            wait_for("fresh synthetic watch packets", fresh, 4)

            def stale():
                state = self.api("/api/state")
                if state["vitals"]["hr"].get("stale"):
                    require(state["links"]["readings"]["stale"] >= 1, "stale reading missing from count")
                    return state["watch"]["packets"]

            packets = wait_for("stale watch heart rate during send pause", stale, 18, interval=0.25)
            wait_for("watch to resume with a fresh reading",
                     lambda: fresh() and self.api("/api/state")["watch"]["packets"] > packets, 10)
        finally:
            done.set()
            watch.join()

    def audit(self):
        audit = self.api("/api/audit")
        require(audit["n_rows"] >= 5 and re.fullmatch("[0-9a-f]{64}", audit["head"] or ""),
                "audit log is missing workflow entries or head hash")
        require(self.api("/api/handoff?all=1")["audit"] == audit, "nurse view shows a different audit result")

    def run(self):
        self.step("dashboard and nurse pages", self.pages, "/", "/index.html", "/handoff", "/handoff.html")
        self.step("STM32 status, environment and raw IMU", self.sensors)
        self.step("watch preflight, override, vibration and fault controls", self.controls)
        self.step("healthy replay scores without alerting", self.healthy)
        self.step("p112060 model activates the alert", self.sepsis_alert)
        task_id = self.step("p112060 opens a nurse handoff task", self.alert_task)
        self.step("unacknowledged alert opens SBAR escalation", self.escalation)
        self.step("named nurse accepts the task", self.accept, task_id)
        self.step("nurse resolves the task", self.resolve, task_id)
        self.step("wearer acknowledges and mutes the alert", self.ack, task_id)
        self.step("replay stops", self.stop_replay)
        self.step('"I feel unwell" opens a live task', self.check_in)
        self.step("FHIR Bundle and QR payload", self.fhir, task_id)
        self.step("stress page, catalogue, scores and summary", self.stress)
        self.step("watch pause makes HR stale and resume refreshes it", self.watch_disconnect)
        self.step("audit chain verifies", self.audit)
        return int(self.failed > 0)


def main():
    try:
        with serve_sim(0) as url:
            return Rehearsal(url).run()
    except Exception as exc:
        print(f"FAIL simulator startup or shutdown ({exc})", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
