"""Labelled replay of held-out PhysioNet 2019 patients, hour by hour, at an accelerated rate.

The board re-scores every replayed hour live (model_runner.RiskModel + news2), exactly as it
would for a real patient. replay_cases.json also stores the scores computed offline, so the
two can be compared (they should match).

    rp = Replay(risk_model)
    rp.cases()                               # [{"id", "kind", "hours", "onset_hour", "label"}]
    rp.start("p008533", seconds_per_hour=2)
    rp.state(now) -> {"active", "case", "hour", "hours", "vitals": {hr, spo2, temp, rr},
                      "risk": {...RiskModel.score...}, "news2": {...}, "timeline": [...],
                      "onset_hour", "hours_to_onset", "label", "done"}
    rp.stop()
"""
import json
import pathlib
import time

from news2 import news2

HERE = pathlib.Path(__file__).parent


def _carried(rows):
    last = [None] * 4
    for r in rows:
        last = [v if v is not None else l for v, l in zip(r, last)]
    return last


class Replay:
    def __init__(self, risk_model, path=HERE / "replay_cases.json"):
        self.rm = risk_model
        data = json.loads(pathlib.Path(path).read_text())
        self.note = data["note"]
        self.by_id = {c["id"]: c for c in data["cases"]}
        self.case, self.t0, self.sph = None, None, 2.0
        self.timeline = []   # per replayed hour: {"hour", "risk", "news2", "alert"}

    def cases(self):
        return [{"id": c["id"], "kind": c["kind"], "hours": len(c["vitals"]), "onset_hour": c["onset_hour"],
                 "start_hour": c.get("start_hour", 0), "end_hour": c.get("end_hour", len(c["vitals"]) - 1),
                 "label": c["label"]} for c in self.by_id.values()]

    def start(self, case_id, seconds_per_hour=2.0):
        self.case = self.by_id[case_id]
        self.t0, self.sph = time.time(), float(seconds_per_hour)
        self.timeline = []

    def stop(self):
        self.case = None

    def state(self, now=None):
        if self.case is None:
            return {"active": False, "cases": self.cases(), "note": self.note}
        now = time.time() if now is None else now
        c = self.case
        start = c.get("start_hour", 0)
        end = c.get("end_hour", len(c["vitals"]) - 1)
        n = end + 1
        hour = min(end, start + int((now - self.t0) / self.sph))
        # score any hours not yet scored, in order (a real device scores once per hour too).
        # The model still sees the full past (up to 24 h), only the display starts at `start`.
        while start + len(self.timeline) <= hour:
            h = start + len(self.timeline)
            hist = c["vitals"][:h + 1]
            hr, o2, t, rr = _carried(hist)
            n2 = news2(rr=rr, spo2=o2, temp=t, hr=hr)
            r = self.rm.score(hist)
            self.timeline.append({"hour": h, "risk": r["risk"], "alert": r["alert"], "news2": n2["score"],
                                  "news2_alert": n2["score"] >= 5 or n2["any_red"],
                                  "expected_risk": c["expected_risk"][h]})
        hist = c["vitals"][:hour + 1]
        hr, o2, t, rr = _carried(hist)
        return {
            "active": True, "case": c["id"], "kind": c["kind"], "label": c["label"], "note": self.note,
            "hour": hour, "start_hour": start, "end_hour": end, "hours": n, "done": hour >= end,
            "seconds_per_hour": self.sph,
            "onset_hour": c["onset_hour"],
            "hours_to_onset": None if c["onset_hour"] is None else c["onset_hour"] - hour,
            "vitals": {"hr": hr, "spo2": o2, "temp": t, "rr": rr},
            "risk": self.rm.score(hist),
            "news2": news2(rr=rr, spo2=o2, temp=t, hr=hr),
            "timeline": self.timeline,
        }
