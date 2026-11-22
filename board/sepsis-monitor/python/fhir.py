"""Offline FHIR R4 export of a handoff task, plus a QR payload a paramedic's device can scan.

    b = bundle(task)                    # vitals / NEWS2 / model default to the task's snapshot
    qr = qr_payload(b, host="192.168.1.20")
    # "SEPSISFHIR:<base64url(deflate(compact JSON))>", or a LAN URL if that is over 1,000 characters
    decode_payload(qr) == lean(b)       # round trip

The Bundle is type "collection": a set of resources, not a transaction. There is no Patient: the device
holds no identity, so the receiver attaches the record to the right person. Replay exports carry the
meta tag "replay" on the Bundle and on every resource.
"""
import base64
import copy
import datetime as dt
import json
import socket
import uuid
import zlib

PREFIX = "SEPSISFHIR:"
QR_MAX_CHARS = 1000
PORT = 8000
UCUM = "http://unitsofmeasure.org"
LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
CAT = "http://terminology.hl7.org/CodeSystem/observation-category"
TAG_SYSTEM = "urn:sepsis-monitor:tag"
TASK_ID_SYSTEM = "urn:sepsis-monitor:task"
DEVICE = "Sepsis monitor prototype (Arduino UNO Q + Wear OS watch)"

# name -> (codings, text, UCUM code, unit display). SpO2 also carries 2708-6, which the R4 core
# oxygen-saturation profile requires next to the pulse-oximetry code 59408-5.
VITALS = {
    "hr": ([("8867-4", "Heart rate")], "Heart rate", "/min", "beats/minute"),
    "spo2": ([("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry"),
              ("2708-6", "Oxygen saturation in Arterial blood")], "SpO2", "%", "%"),
    "rr": ([("9279-1", "Respiratory rate")], "Respiratory rate", "/min", "breaths/minute"),
    "temp": ([("8310-5", "Body temperature")], "Body temperature", "Cel", "°C"),
}
# UK SNOMED CT concept for the NEWS2 total score (as used in NHS England NEWS2 FHIR guidance).
NEWS2_CODE = ("1104051000000101", "Royal College of Physicians NEWS2 (National Early Warning Score 2) total score")
SRC_TEXT = {"watch": "Wear OS watch (PPG)", "imu": "Chest accelerometer on the board",
            "override": "Entered manually on the dashboard", "manual_oral": "Oral thermometer, typed in by a person",
            "replay": "Recorded ICU data (replay)"}
TASK_STATUS = {"pending": "requested", "accepted": "accepted", "resolved": "completed", "cancelled": "cancelled"}
REQUESTER = {"model": "Edge Impulse risk model on the device", "news2": "NEWS2 rule on the device",
             "wearer": "The wearer or carer (manual report)", "rule": "Pathway rule on the device"}


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _uid(task_id, name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:sepsis-monitor:{task_id}:{name}"))


def _val(x):
    return x.get("v") if isinstance(x, dict) else x


def bundle(task, vitals=None, news2=None, model=None, device=DEVICE):
    """FHIR R4 collection Bundle: one Task, five Observations (HR, SpO2, RR, temperature, NEWS2),
    and a Provenance naming the device and the model engine. Missing readings get a dataAbsentReason.

    vitals: {name: value} or handoff.compact_snapshot()'s {name: {"v", "src", "age_s"}}.
    """
    snap = task.get("snapshot") or {}
    vitals = vitals if vitals is not None else snap.get("vitals") or {}
    news2 = news2 if news2 is not None else snap.get("news2") or {}
    model = model if model is not None else snap.get("model") or {}
    tid = task["id"]
    taken = snap.get("at") or task["created_at"]
    last = max(t for t in (task["created_at"], task.get("wearer_ack_at"), task.get("accepted_at"),
                           task.get("resolved_at")) if t)
    meta = {"meta": {"tag": [{"system": TAG_SYSTEM, "code": "replay",
                              "display": "Replay of a recorded ICU case, not a live patient"}]}} if task.get("replay") else {}
    url = lambda name: "urn:uuid:" + _uid(tid, name)
    entries = []

    obs_refs = []
    for name, (codings, text, ucum, unit) in VITALS.items():
        x = vitals.get(name)
        v = _val(x)
        src = x.get("src") if isinstance(x, dict) else None
        age = x.get("age_s") if isinstance(x, dict) else None
        r = {"resourceType": "Observation", "id": _uid(tid, name), **copy.deepcopy(meta), "status": "final",
             "category": [{"coding": [{"system": CAT, "code": "vital-signs"}]}],
             "code": {"coding": [{"system": LOINC, "code": c, "display": d} for c, d in codings], "text": text},
             "effectiveDateTime": _iso(taken - (age or 0))}
        if v is None:
            r["dataAbsentReason"] = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                                                 "code": "not-performed"}],
                                     "text": "Wrist skin temperature is not core temperature" if name == "temp"
                                     else "Not measured"}
        else:
            r["valueQuantity"] = {"value": v, "unit": unit, "system": UCUM, "code": ucum}
        if src:
            r["device"] = {"display": SRC_TEXT.get(src, src)}
        entries.append((url(name), r))
        obs_refs.append({"reference": url(name)})

    parts = news2.get("parts") or {}
    n2 = {"resourceType": "Observation", "id": _uid(tid, "news2"), **copy.deepcopy(meta), "status": "final",
          "category": [{"coding": [{"system": CAT, "code": "survey"}]}],
          "code": {"coding": [{"system": SNOMED, "code": NEWS2_CODE[0], "display": NEWS2_CODE[1]}], "text": "NEWS2 total"},
          "effectiveDateTime": _iso(taken),
          "derivedFrom": obs_refs,
          "note": [{"text": "Partial NEWS2 from " + (", ".join(f"{k} {p}" for k, p in parts.items()) or "no vitals")
                    + ". Blood pressure, consciousness and supplemental oxygen were not measured and scored 0."}]}
    if news2.get("score") is None:
        n2["dataAbsentReason"] = {"text": "Not scored"}
    else:
        n2["valueInteger"] = int(news2["score"])
    entries.append((url("news2"), n2))

    sbar = task.get("sbar") or {}
    assess = sbar.get("assessment") or []
    notes = [("S", sbar.get("situation")), ("B", sbar.get("background")),
             ("A", " ".join(assess) if isinstance(assess, list) else assess), ("R", sbar.get("recommendation"))]
    risk = model.get("risk")
    if risk is not None:
        thr = model.get("threshold")
        notes.append(("Model", f"risk {risk:.0f}%" + (f" (alert threshold {thr:.0f}%)" if thr is not None else "")))
    notes.append(("Note", "Decision support from a prototype, not a diagnosis."))
    t = {"resourceType": "Task", "id": _uid(tid, "task"), **copy.deepcopy(meta),
         "identifier": [{"system": TASK_ID_SYSTEM, "value": tid}],
         "status": TASK_STATUS.get(task["status"], "requested"),
         "intent": "proposal",
         "priority": "urgent" if task.get("priority", "urgent") == "urgent" else "routine",
         "code": {"text": f"Clinical review: {task['kind']}"},
         "description": sbar.get("situation") or task["kind"],
         "authoredOn": _iso(task["created_at"]), "lastModified": _iso(last),
         "requester": {"display": REQUESTER.get(task["source"], task["source"])},
         "note": [{"text": f"{k}: {v}"} for k, v in notes if v],
         "input": [{"type": {"text": "observation"}, "valueReference": ref} for ref in obs_refs + [{"reference": url("news2")}]]}
    if task.get("accepted_by"):
        t["owner"] = {"display": f"Nurse {task['accepted_by']}"}
    if task.get("accepted_at"):
        t["executionPeriod"] = {"start": _iso(task["accepted_at"])}
        if task.get("resolved_at"):
            t["executionPeriod"]["end"] = _iso(task["resolved_at"])
    if task.get("wearer_ack_at"):
        t["input"].append({"type": {"text": "wearer acknowledged"}, "valueDateTime": _iso(task["wearer_ack_at"])})
    out = []
    if task.get("action"):
        out.append({"type": {"text": "action"}, "valueString": task["action"]})
    if task.get("outcome"):
        out.append({"type": {"text": "outcome"}, "valueCode": task["outcome"]})
    if out:
        t["output"] = out
    entries.insert(0, (url("task"), t))

    engine = model.get("engine") or "not loaded"
    prov = {"resourceType": "Provenance", "id": _uid(tid, "provenance"), **copy.deepcopy(meta),
            "target": [{"reference": u} for u, _ in entries], "recorded": _iso(last),
            "agent": [
                {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                                      "code": "performer"}]}, "who": {"display": device}},
                {"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                                      "code": "assembler"}]}, "who": {"display": f"Edge Impulse model, engine {engine}"}}]}
    entries.append((url("provenance"), prov))

    b = {"resourceType": "Bundle", "id": _uid(tid, "bundle"), **copy.deepcopy(meta), "type": "collection",
         "timestamp": _iso(last), "entry": [{"fullUrl": u, "resource": r} for u, r in entries]}
    return b


def _strip(obj, keys):
    if isinstance(obj, dict):
        return {k: _strip(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip(v, keys) for v in obj]
    return obj


def lean(b):
    """The QR copy of a bundle: codes and values kept; coding displays, the long SBAR recommendation
    (fixed advice text) and per-resource ids dropped. Still a valid R4 Bundle."""
    b = _strip(b, {"display"})
    for e in b["entry"]:
        r = e["resource"]
        r.pop("id", None)
        if r["resourceType"] == "Task":
            r["note"] = [n for n in r.get("note", []) if not n["text"].startswith(("R:", "B:"))]
    return b


def _pack(b):
    raw = json.dumps(b, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    z = zlib.compressobj(9, zlib.DEFLATED, -15)   # raw deflate, no zlib header
    return PREFIX + base64.urlsafe_b64encode(z.compress(raw) + z.flush()).decode("ascii").rstrip("=")


def decode_payload(payload):
    """Inverse of the inline QR payload."""
    if not payload.startswith(PREFIX):
        raise ValueError("not a SEPSISFHIR payload")
    s = payload[len(PREFIX):]
    data = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    return json.loads(zlib.decompress(data, -15).decode("utf-8"))


def lan_ip():
    """This board's address on the LAN (no packet is sent). 127.0.0.1 if there is no route."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def task_id_of(b):
    for e in b["entry"]:
        r = e["resource"]
        if r["resourceType"] == "Task":
            return r["identifier"][0]["value"]
    raise ValueError("bundle has no Task")


def qr_payload(bundle_, host=None, port=PORT):
    """'SEPSISFHIR:' + base64url(deflate(compact JSON of lean(bundle))), or, if that is over
    1,000 characters, the LAN URL of the full bundle: http://<host>:8000/api/fhir/<task_id>."""
    p = _pack(lean(bundle_))
    if len(p) <= QR_MAX_CHARS:
        return p
    return f"http://{host or lan_ip()}:{port}/api/fhir/{task_id_of(bundle_)}"
