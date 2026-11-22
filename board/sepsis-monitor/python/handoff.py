"""Owned handoff: an alert becomes a task that a named nurse accepts and resolves.

    h = Handoff()                                    # python/data/handoff.db
    t = h.open_task("model", "alert", sbar, snap)    # idempotent per episode (live/replay + kind)
    h.accept(t["id"], "Sam")                         # pending -> accepted
    h.resolve(t["id"], "Phoned, advised 111", "advised_111")   # accepted -> resolved
    h.verify_audit()                                 # (True, n_rows) unless the log was altered

Status flow: pending -> accepted -> resolved. A task can also be "cancelled" by the system
(for example the replay that raised it was stopped); that is never shown as a nurse's decision.

Every change appends a row to an audit table. Each row stores the full task after the change and
the SHA-256 of (previous row's hash + this row's JSON), so editing or deleting an earlier row, or
editing a task without logging it, breaks the chain. SQLite triggers also refuse UPDATE/DELETE on
the audit table. Deleting the newest rows is only detectable against a copy of audit_head().

Decision support only: a task asks a person to review; it is not a diagnosis.
"""
import hashlib
import json
import pathlib
import sqlite3
import threading
import time
import uuid

SOURCES = ("model", "news2", "wearer", "rule")
PRIORITIES = ("urgent", "review")
OUTCOMES = ("advised_111", "call_999", "home_visit", "no_action", "other")
OPEN = ("pending", "accepted")
GENESIS = "0" * 64
DEFAULT_DB = pathlib.Path(__file__).parent / "data" / "handoff.db"
MAX_TEXT = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, episode TEXT NOT NULL, replay INTEGER NOT NULL, source TEXT NOT NULL,
  kind TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL,
  sbar TEXT NOT NULL, snapshot TEXT NOT NULL, created_at REAL NOT NULL,
  wearer_ack_at REAL, accepted_at REAL, accepted_by TEXT, resolved_at REAL, action TEXT, outcome TEXT);
CREATE INDEX IF NOT EXISTS tasks_episode ON tasks(episode, status);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY, body TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


class HandoffError(ValueError):
    """A request the task can't take (unknown id, wrong status, bad outcome). `code` is the HTTP status."""

    def __init__(self, msg, code=409):
        super().__init__(msg)
        self.code = code


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(prev, body):
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def _text(value, what, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{what} is required", 400)
    value = " ".join(value.split())
    if len(value) > limit:
        raise HandoffError(f"{what} is longer than {limit} characters", 400)
    return value


class Handoff:
    def __init__(self, db_path=DEFAULT_DB):
        db_path = pathlib.Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()   # the HTTP server is threaded; one writer at a time
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def close(self):
        self._db.close()

    # ---- internals -------------------------------------------------------------------------
    @staticmethod
    def _task(row):
        if row is None:
            return None
        t = dict(row)
        t["replay"] = bool(t["replay"])
        t["sbar"] = json.loads(t["sbar"])
        t["snapshot"] = json.loads(t["snapshot"])
        return t

    def _get(self, task_id):
        return self._task(self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    def _need(self, task_id):
        t = self._get(task_id)
        if t is None:
            raise HandoffError(f"no task {task_id!r}", 404)
        return t

    def _update(self, task_id, now, event, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._db.execute(f"UPDATE tasks SET {cols} WHERE id = ?", (*fields.values(), task_id))
        t = self._get(task_id)
        self._audit(event, t, now)
        return t

    def _audit(self, event, task, now):
        last = self._db.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (last["seq"] + 1, last["hash"]) if last else (1, GENESIS)
        body = _canon({"seq": seq, "at": now, "event": event, "task_id": task["id"], "task": task})
        self._db.execute("INSERT INTO audit (seq, body, prev_hash, hash) VALUES (?, ?, ?, ?)",
                         (seq, body, prev, _sha(prev, body)))

    # ---- API -------------------------------------------------------------------------------
    def open_task(self, source, kind, sbar, snapshot, replay=False, priority="urgent", now=None):
        """Open a task, or return the one already open for this episode (replay flag + kind)."""
        if source not in SOURCES:
            raise HandoffError(f"source must be one of {SOURCES}", 400)
        if priority not in PRIORITIES:
            raise HandoffError(f"priority must be one of {PRIORITIES}", 400)
        kind = _text(kind, "kind", 64)
        episode = f"{'replay' if replay else 'live'}:{kind}"
        now = time.time() if now is None else now
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT * FROM tasks WHERE episode = ? AND status IN ('pending', 'accepted') "
                "ORDER BY created_at LIMIT 1", (episode,)).fetchone()
            if row is not None:
                return self._task(row)
            task_id = uuid.uuid4().hex[:12]
            self._db.execute(
                "INSERT INTO tasks (id, episode, replay, source, kind, priority, status, sbar, snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                (task_id, episode, int(bool(replay)), source, kind, priority,
                 _canon(sbar or {}), _canon(snapshot or {}), now))
            t = self._get(task_id)
            self._audit("open", t, now)
            return t

    def accept(self, task_id, nurse_name, now=None):
        nurse = _text(nurse_name, "nurse name", 60)
        now = time.time() if now is None else now
        with self._lock, self._db:
            t = self._need(task_id)
            if t["status"] == "accepted" and t["accepted_by"].lower() == nurse.lower():
                return t   # a double tap by the same nurse
            if t["status"] != "pending":
                who = f" by {t['accepted_by']}" if t["accepted_by"] else ""
                raise HandoffError(f"task is already {t['status']}{who}")
            return self._update(task_id, now, "accept", status="accepted", accepted_at=now, accepted_by=nurse)

    def resolve(self, task_id, action_text, outcome, now=None):
        action = _text(action_text, "action")
        if outcome not in OUTCOMES:
            raise HandoffError(f"outcome must be one of {OUTCOMES}", 400)
        now = time.time() if now is None else now
        with self._lock, self._db:
            t = self._need(task_id)
            if t["status"] != "accepted":
                raise HandoffError(f"only an accepted task can be resolved (this one is {t['status']})")
            return self._update(task_id, now, "resolve", status="resolved", resolved_at=now,
                                action=action, outcome=outcome)

    def wearer_ack(self, task_id, now=None):
        """The wearer has seen the alert. Records the first acknowledgement only."""
        now = time.time() if now is None else now
        with self._lock, self._db:
            t = self._need(task_id)
            if t["wearer_ack_at"] is not None or t["status"] == "cancelled":
                return t
            return self._update(task_id, now, "wearer_ack", wearer_ack_at=now)

    def cancel(self, task_id, reason, now=None):
        """System close (e.g. its replay was stopped). Not a nurse decision, so no outcome is set."""
        reason = _text(reason, "reason")
        now = time.time() if now is None else now
        with self._lock, self._db:
            t = self._need(task_id)
            if t["status"] not in OPEN:
                return t
            return self._update(task_id, now, "cancel", status="cancelled", resolved_at=now, action=reason)

    def cancel_open(self, replay, reason, now=None):
        """Cancel every open task of one mode (call with replay=True when a replay starts or stops)."""
        ids = [t["id"] for t in self.list(active_only=True, replay=replay)]
        return [self.cancel(i, reason, now) for i in ids]

    def list(self, active_only=True, replay=None, limit=100):
        """Open tasks (pending first, newest first), or all tasks newest first."""
        where, args = [], []
        if active_only:
            where.append("status IN ('pending', 'accepted')")
        if replay is not None:
            where.append("replay = ?")
            args.append(int(bool(replay)))
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY (status = 'pending') DESC, created_at DESC LIMIT ?"
        with self._lock:
            return [self._task(r) for r in self._db.execute(sql, (*args, int(limit))).fetchall()]

    def get(self, task_id):
        with self._lock:
            return self._get(task_id)

    def wearer_receipt(self, replay=False, now=None, within_s=24 * 3600):
        """What the wearer's screen shows: who has the newest task and when. None if there is none."""
        now = time.time() if now is None else now
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM tasks WHERE replay = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
                (int(bool(replay)), now - within_s)).fetchone()
        t = self._task(row)
        if t is None:
            return None
        hm = lambda ts: time.strftime("%H:%M", time.localtime(ts))
        text = {
            "pending": f"Sent to the nurse team at {hm(t['created_at'])}. Waiting for a nurse to accept.",
            "accepted": f"Nurse {t['accepted_by']} has your alert (accepted {hm(t['accepted_at'] or now)}).",
            "resolved": f"Nurse {t['accepted_by']} closed it at {hm(t['resolved_at'] or now)}: {t['action']}",
            "cancelled": f"Closed by the system at {hm(t['resolved_at'] or now)}: {t['action']}",
        }[t["status"]]
        return {"task_id": t["id"], "status": t["status"], "accepted_by": t["accepted_by"], "text": text}

    def audit_head(self):
        """(n_rows, last hash). Write it down elsewhere to detect deletion of the newest rows."""
        with self._lock:
            row = self._db.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        return (row["seq"], row["hash"]) if row else (0, GENESIS)

    def verify_audit(self):
        """Recompute the hash chain and check every task row matches its last audited state.

        Returns (ok, n_rows)."""
        with self._lock:
            rows = self._db.execute("SELECT seq, body, prev_hash, hash FROM audit ORDER BY seq").fetchall()
            tasks = {r["id"]: self._task(r) for r in self._db.execute("SELECT * FROM tasks").fetchall()}
        prev, last_state = GENESIS, {}
        for i, r in enumerate(rows, 1):
            if r["seq"] != i or r["prev_hash"] != prev or _sha(prev, r["body"]) != r["hash"]:
                return False, len(rows)
            try:
                b = json.loads(r["body"])
            except json.JSONDecodeError:
                return False, len(rows)
            if b.get("seq") != i:
                return False, len(rows)
            last_state[b["task_id"]] = b["task"]
            prev = r["hash"]
        return last_state == tasks, len(rows)


# ---- snapshot helper ----------------------------------------------------------------------------
def _model(m):
    m = m or {}
    return {k: m.get(k) for k in ("risk", "threshold", "engine", "alert", "note")}


def compact_snapshot(snap, rs=None, manual=None):
    """What the nurse page and the FHIR export need, from main.py's snapshot() (live) or replay_state().

    vitals: {hr|spo2|rr|temp: {"v", "src", "age_s"}}. age_s is how old the reading was when the task
    was opened (None if unknown). A manual oral temperature from a check-in replaces "temp".
    Wrist skin temperature is kept apart as context ("skin_c") and is never treated as core temperature.
    """
    snap = snap or {}
    now = snap.get("now", time.time())
    if rs and rs.get("active"):
        rv = rs.get("vitals") or {}
        out = {
            "at": now,
            "replay": {k: rs.get(k) for k in ("case", "label", "hour", "hours_to_onset")},
            "vitals": {k: {"v": rv.get(k), "src": "replay", "age_s": None} for k in ("hr", "spo2", "rr", "temp")},
            "skin_c": None,
            "news2": rs.get("news2"),
            "model": _model(rs.get("risk")),
        }
    else:
        sv = snap.get("vitals") or {}
        watch_age = (snap.get("watch") or {}).get("last_age_s")
        rr_at = (snap.get("rr_detail") or {}).get("at")
        vitals = {}
        for k in ("hr", "spo2", "rr", "temp"):
            x = sv.get(k) or {}
            age = x.get("age_s")
            if age is None and x.get("v") is not None:
                if x.get("src") == "override":
                    age = None
                elif k == "hr" and x.get("src") == "watch":
                    age = watch_age
                elif k == "rr" and x.get("src") == "imu" and rr_at:
                    age = now - rr_at
            vitals[k] = {"v": x.get("v"), "src": x.get("src"), "age_s": None if age is None else round(age)}
        out = {"at": now, "replay": None, "vitals": vitals, "skin_c": (sv.get("skin") or {}).get("v"),
               "news2": snap.get("news2"), "model": _model(snap.get("risk"))}
    if manual and manual.get("oral_temp_c") is not None:
        out["vitals"]["temp"] = {"v": manual["oral_temp_c"], "src": "manual_oral", "age_s": 0}
    return out
