"""Tests for handoff.py, pathways.py, and fhir.py.

Run: .venv/Scripts/python.exe -m unittest board/sepsis-monitor/python/test_handoff_pathways_fhir.py
"""
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

import fhir  # noqa: E402
import handoff  # noqa: E402
import pathways  # noqa: E402


SAMPLE_SBAR = {
    "situation": "Alert raised by Edge Impulse risk model (72%).",
    "background": "Live wearable monitoring. No record of medicines.",
    "assessment": ["Heart rate up +18 bpm over 6 h.", "Resp rate 24 /min."],
    "recommendation": "Check the wearer and consider clinical review.",
    "disclaimer": "Prototype only.",
}

SAMPLE_SNAP = {
    "at": 1763740000.0,
    "replay": None,
    "vitals": {
        "hr": {"v": 112.0, "src": "watch", "age_s": 4},
        "spo2": {"v": 94.0, "src": "watch", "age_s": 30},
        "rr": {"v": 24.0, "src": "imu", "age_s": 5},
        "temp": {"v": None, "src": None, "age_s": None},
    },
    "skin_c": 34.2,
    "news2": {"score": 5, "any_red": False, "parts": {"hr": 2, "spo2": 1, "rr": 2}, "missing": ["temp"]},
    "model": {"risk": 72.0, "threshold": 55.0, "engine": "eim", "alert": True, "note": ""},
}


class TestHandoff(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self._tmp.name) / "handoff.db"
        self.h = handoff.Handoff(self.db)

    def tearDown(self):
        self.h.close()
        self._tmp.cleanup()

    def test_lifecycle_and_idempotency(self):
        t1 = self.h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, now=1000.0)
        t2 = self.h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, now=1010.0)
        self.assertEqual(t1["id"], t2["id"])
        self.assertEqual(t1["status"], "pending")

        rec_pending = self.h.wearer_receipt(replay=False, now=1015.0)
        self.assertEqual(rec_pending["status"], "pending")
        self.assertIn("Waiting for a nurse", rec_pending["text"])

        # Wearer ack
        ta = self.h.wearer_ack(t1["id"], now=1020.0)
        self.assertEqual(ta["wearer_ack_at"], 1020.0)

        # Accept + double tap by same nurse
        t_acc = self.h.accept(t1["id"], "Sam", now=1050.0)
        self.assertEqual(t_acc["status"], "accepted")
        self.assertEqual(t_acc["accepted_by"], "Sam")
        t_acc2 = self.h.accept(t1["id"], "sam", now=1055.0)
        self.assertEqual(t_acc2["accepted_at"], 1050.0)

        # Second nurse cannot steal it
        with self.assertRaises(handoff.HandoffError) as ctx:
            self.h.accept(t1["id"], "Pat", now=1060.0)
        self.assertEqual(ctx.exception.code, 409)

        rec_acc = self.h.wearer_receipt(replay=False, now=1065.0)
        self.assertIn("Nurse Sam has your alert", rec_acc["text"])

        # Resolve
        t_res = self.h.resolve(t1["id"], "Phoned wearer, advised 111", "advised_111", now=1200.0)
        self.assertEqual(t_res["status"], "resolved")
        self.assertEqual(t_res["outcome"], "advised_111")

        # Audit chain valid
        ok, n = self.h.verify_audit()
        self.assertTrue(ok)
        self.assertEqual(n, 4)  # open, wearer_ack, accept, resolve

    def test_resolve_requires_accepted(self):
        t = self.h.open_task("wearer", "concern", SAMPLE_SBAR, SAMPLE_SNAP, now=1000.0)
        with self.assertRaises(handoff.HandoffError):
            self.h.resolve(t["id"], "Done", "no_action", now=1010.0)

    def test_cancel_open_replay_only(self):
        live = self.h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, replay=False, now=1000.0)
        rep = self.h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, replay=True, now=1001.0)
        cancelled = self.h.cancel_open(replay=True, reason="Replay stopped", now=1050.0)
        self.assertEqual([c["id"] for c in cancelled], [rep["id"]])
        self.assertEqual(self.h.get(rep["id"])["status"], "cancelled")
        self.assertEqual(self.h.get(live["id"])["status"], "pending")

    def test_audit_detects_tampering(self):
        t = self.h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, now=1000.0)
        self.assertTrue(self.h.verify_audit()[0])
        # Direct UPDATE on tasks without audit entry breaks verify_audit
        con = sqlite3.connect(str(self.db))
        con.execute("UPDATE tasks SET status = 'resolved' WHERE id = ?", (t["id"],))
        con.commit()
        # Audit table triggers block UPDATE/DELETE
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("DELETE FROM audit")
        con.close()
        self.assertFalse(self.h.verify_audit()[0])


class TestPathways(unittest.TestCase):
    def test_chemo_fever_triggers_urgent_nice_cg151(self):
        prof = {"type": "chemo", "last_treatment_date": "2026-11-15"}
        manual = {"oral_temp_c": 38.1, "feel_unwell": False, "something_wrong": False, "soft_signs": [], "by": "wearer"}
        now = 1795180800.0  # 2026-11-21
        trigs = pathways.evaluate(prof, manual=manual, now=now)
        self.assertEqual(len(trigs), 1)
        self.assertEqual(trigs[0]["rule"], "chemo_neutropenic_sepsis")
        self.assertEqual(trigs[0]["severity"], "urgent")
        self.assertIn("NICE CG151", trigs[0]["source_guideline"])

    def test_skin_temp_never_triggers_chemo_rule(self):
        prof = {"type": "chemo", "last_treatment_date": "2026-11-15"}
        vitals = {"skin": {"v": 39.0}, "temp": {"v": 39.0}}
        trigs = pathways.evaluate(prof, vitals=vitals, manual={}, now=1795180800.0)
        self.assertEqual(trigs, [])

    def test_marthas_rule_and_new_confusion(self):
        manual = {"feel_unwell": True, "soft_signs": ["new_confusion"], "by": "carer"}
        trigs = pathways.evaluate({"type": "general"}, manual=manual, now=1795180800.0)
        rules = [t["rule"] for t in trigs]
        self.assertEqual(rules[0], "new_confusion")  # urgent sorted first
        self.assertIn("concern", rules)

    def test_care_home_soft_signs(self):
        prof = {"type": "care_home", "care_home_name": "Oak House"}
        one = pathways.evaluate(prof, manual={"soft_signs": ["reduced_mobility"]}, now=1795180800.0)
        self.assertEqual(one, [])
        two = pathways.evaluate(prof, manual={"soft_signs": ["reduced_mobility", "not_passing_urine"]}, now=1795180800.0)
        self.assertEqual([t["rule"] for t in two], ["soft_signs"])

    def test_validate_checkin_rejects_implausible_temp(self):
        m, errs = pathways.validate_checkin({"oral_temp_c": 99.0})
        self.assertIsNone(m)
        self.assertTrue(errs)


class TestFhir(unittest.TestCase):
    def test_bundle_and_qr_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = handoff.Handoff(pathlib.Path(tmp) / "h.db")
            t = h.open_task("model", "alert", SAMPLE_SBAR, SAMPLE_SNAP, replay=True, now=1763740000.0)
            t = h.accept(t["id"], "Sam", now=1763740060.0)
            h.close()

        b = fhir.bundle(t)
        self.assertEqual(b["resourceType"], "Bundle")
        self.assertEqual(b["type"], "collection")
        types = [e["resource"]["resourceType"] for e in b["entry"]]
        self.assertEqual(types.count("Task"), 1)
        self.assertEqual(types.count("Observation"), 5)
        self.assertEqual(types.count("Provenance"), 1)
        # Replay tag on bundle and all resources
        self.assertEqual(b["meta"]["tag"][0]["code"], "replay")
        for e in b["entry"]:
            self.assertEqual(e["resource"]["meta"]["tag"][0]["code"], "replay")
        # Missing temperature has dataAbsentReason
        temp_obs = [e["resource"] for e in b["entry"]
                    if e["resource"]["resourceType"] == "Observation"
                    and e["resource"]["code"]["text"] == "Body temperature"][0]
        self.assertIn("dataAbsentReason", temp_obs)
        self.assertNotIn("valueQuantity", temp_obs)

        # QR payload round trip
        qr = fhir.qr_payload(b, host="192.168.1.50")
        if qr.startswith(fhir.PREFIX):
            decoded = fhir.decode_payload(qr)
            self.assertEqual(decoded, fhir.lean(b))
            self.assertLessEqual(len(qr), fhir.QR_MAX_CHARS)
        else:
            self.assertTrue(qr.startswith("http://192.168.1.50:8000/api/fhir/"))


if __name__ == "__main__":
    unittest.main()
