"""Data-access functions. All SQL outside migrations lives here (NFR-009)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from typing import Any

from .db import utcnow


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


# --- Users -------------------------------------------------------------------

def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict | None:
    return _row(conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone())


def create_user(conn, username: str, display_name: str, role: str, password_hash: str, user_id: str | None = None) -> str:
    user_id = user_id or f"USR-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO users (id, username, display_name, role, password_hash, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, username, display_name, role, password_hash, utcnow()),
    )
    return user_id


def list_users(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, username, display_name, role, active, created_at FROM users ORDER BY username")]


# --- Patients and encounters -----------------------------------------------------

def create_patient(conn, given_name: str, family_name: str, sex: str, birth_year: int | None,
                   created_by: str | None, patient_id: str | None = None) -> str:
    patient_id = patient_id or _new_id("SYN-P")
    conn.execute(
        "INSERT INTO patients (id, given_name, family_name, sex, birth_year, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (patient_id, given_name, family_name, sex, birth_year, created_by, utcnow()),
    )
    return patient_id


def get_patient(conn, patient_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone())
    if row is None:
        raise NotFound(f"patient {patient_id} not found")
    return row


def search_patients(conn, query: str | None, limit: int = 50) -> list[dict]:
    if query:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM patients WHERE id LIKE ? OR given_name LIKE ? OR family_name LIKE ?"
            " ORDER BY family_name LIMIT ?", (like, like, like, limit))
    else:
        rows = conn.execute("SELECT * FROM patients ORDER BY family_name LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def upsert_record_source(conn, patient_id: str, source_type: str, status: str, note: str | None) -> None:
    conn.execute(
        """INSERT INTO record_sources (id, patient_id, source_type, status, note, updated_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(patient_id, source_type) DO UPDATE SET status=excluded.status, note=excluded.note,
           updated_at=excluded.updated_at""",
        (str(uuid.uuid4()), patient_id, source_type, status, note, utcnow()),
    )


def list_record_sources(conn, patient_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT source_type, status, note, updated_at FROM record_sources WHERE patient_id = ?", (patient_id,))]


def create_encounter(conn, patient_id: str, facility_code: str, complaint_code: str, chief_complaint: str,
                     created_by: str | None, *, arrived_at: str | None = None, status: str = "open",
                     record_source: str = "electronic_record", complaint_source: str = "patient_reported",
                     encounter_id: str | None = None) -> str:
    get_patient(conn, patient_id)
    encounter_id = encounter_id or _new_id("SYN-E")
    conn.execute(
        """INSERT INTO encounters (id, patient_id, facility_code, arrived_at, complaint_code, chief_complaint,
           complaint_source, status, record_source, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (encounter_id, patient_id, facility_code, arrived_at or utcnow(), complaint_code, chief_complaint,
         complaint_source, status, record_source, created_by, utcnow()),
    )
    return encounter_id


def get_encounter(conn, encounter_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM encounters WHERE id = ?", (encounter_id,)).fetchone())
    if row is None:
        raise NotFound(f"encounter {encounter_id} not found")
    return row


def list_encounters(conn, *, status: str | None = None, patient_id: str | None = None, limit: int = 100) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("e.status = ?")
        params.append(status)
    if patient_id:
        clauses.append("e.patient_id = ?")
        params.append(patient_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT e.*, p.given_name, p.family_name, q.priority AS synthetic_queue_priority,
            (SELECT status FROM review_requests r WHERE r.encounter_id = e.id ORDER BY r.requested_at DESC LIMIT 1)
              AS latest_review_status
            FROM encounters e JOIN patients p ON p.id = e.patient_id
            LEFT JOIN synthetic_queue q ON q.encounter_id = e.id
            {where} ORDER BY e.arrived_at DESC LIMIT ?""", (*params, limit))
    return [dict(r) for r in rows]


def prior_encounters(conn, patient_id: str, before: str, exclude_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM encounters WHERE patient_id = ? AND arrived_at < ? AND id != ? ORDER BY arrived_at DESC",
        (patient_id, before, exclude_id))]


def notes_for_encounters(conn, encounter_ids: list[str]) -> list[dict]:
    if not encounter_ids:
        return []
    marks = ",".join("?" * len(encounter_ids))
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM clinical_notes WHERE encounter_id IN ({marks}) ORDER BY recorded_at", encounter_ids)]


def add_note(conn, encounter_id: str, category: str, content: str, source_type: str, *,
             source_ref: str | None = None, recorded_by: str | None = None, recorded_at: str | None = None) -> str:
    note_id = f"NOTE-{uuid.uuid4().hex[:10]}"
    conn.execute(
        """INSERT INTO clinical_notes (id, encounter_id, category, content, source_type, source_ref,
           recorded_by, recorded_at) VALUES (?,?,?,?,?,?,?,?)""",
        (note_id, encounter_id, category, content, source_type, source_ref, recorded_by, recorded_at or utcnow()),
    )
    return note_id


# --- Observations and symptoms -----------------------------------------------------

def add_observation(conn, encounter_id: str, code: str, *, value_num: float | None, value_text: str | None,
                    unit: str | None, source_type: str, verification_status: str, recorded_by: str | None,
                    source_ref: str | None = None, recorded_at: str | None = None) -> str:
    obs_id = f"OBS-{uuid.uuid4().hex[:10]}"
    now = recorded_at or utcnow()
    verified = verification_status == "verified"
    conn.execute(
        """INSERT INTO observations (id, encounter_id, code, value_num, value_text, unit, source_type,
           verification_status, source_ref, recorded_by, recorded_at, verified_by, verified_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (obs_id, encounter_id, code, value_num, value_text, unit, source_type, verification_status, source_ref,
         recorded_by, now, recorded_by if verified else None, now if verified else None),
    )
    return obs_id


def get_observation(conn, obs_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM observations WHERE id = ?", (obs_id,)).fetchone())
    if row is None:
        raise NotFound(f"observation {obs_id} not found")
    return row


def observations_for_encounters(conn, encounter_ids: list[str]) -> list[dict]:
    if not encounter_ids:
        return []
    marks = ",".join("?" * len(encounter_ids))
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM observations WHERE encounter_id IN ({marks}) ORDER BY recorded_at", encounter_ids)]


def verify_observation(conn, obs_id: str, user_id: str) -> None:
    obs = get_observation(conn, obs_id)
    if obs["status"] != "active":
        raise Conflict("only active observations can be verified")
    conn.execute("UPDATE observations SET verification_status='verified', verified_by=?, verified_at=? WHERE id=?",
                 (user_id, utcnow(), obs_id))


def set_observation_status(conn, obs_id: str, status: str, user_id: str, reason: str) -> None:
    obs = get_observation(conn, obs_id)
    if obs["status"] != "active":
        raise Conflict(f"observation is already {obs['status']}")
    conn.execute("UPDATE observations SET status=?, status_changed_by=?, status_reason=? WHERE id=?",
                 (status, user_id, reason, obs_id))


def add_symptom(conn, encounter_id: str, code: str, present: bool, source_type: str, recorded_by: str | None,
                recorded_at: str | None = None) -> str:
    sym_id = f"SYM-{uuid.uuid4().hex[:10]}"
    conn.execute(
        "INSERT INTO symptoms (id, encounter_id, code, present, source_type, recorded_by, recorded_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (sym_id, encounter_id, code, int(present), source_type, recorded_by, recorded_at or utcnow()),
    )
    return sym_id


def symptoms_for_encounter(conn, encounter_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM symptoms WHERE encounter_id = ? ORDER BY recorded_at", (encounter_id,))]


# --- Evaluations, reviews, actions, queue ------------------------------------------------

def save_evaluation(conn, encounter_id: str, result: dict, created_by: str) -> str:
    eval_id = f"EVAL-{uuid.uuid4().hex[:10]}"
    conn.execute(
        """INSERT INTO protocol_evaluations (id, encounter_id, protocol_id, protocol_version, protocol_sha256,
           protocol_status, status, proposed_priority, urgent_flag, result_json, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eval_id, encounter_id, result["protocol_id"], result["protocol_version"], result.get("protocol_sha256"),
         result.get("protocol_status"), result["status"], result.get("proposed_priority"),
         int(bool(result.get("urgent_flag"))), json.dumps(result), created_by, utcnow()),
    )
    return eval_id


def get_evaluation(conn, eval_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM protocol_evaluations WHERE id = ?", (eval_id,)).fetchone())
    if row is None:
        raise NotFound(f"evaluation {eval_id} not found")
    row["result"] = json.loads(row.pop("result_json"))
    return row


def get_review(conn, review_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM review_requests WHERE id = ?", (review_id,)).fetchone())
    if row is None:
        raise NotFound(f"review {review_id} not found")
    summary = row.pop("summary_json")
    row["summary"] = json.loads(summary) if summary else None
    return row


def get_review_by_idempotency_key(conn, key: str) -> dict | None:
    row = conn.execute("SELECT id FROM review_requests WHERE idempotency_key = ?", (key,)).fetchone()
    return get_review(conn, row["id"]) if row else None


def list_reviews(conn, status: str | None = None, limit: int = 100) -> list[dict]:
    where, params = ("WHERE r.status = ?", [status]) if status else ("", [])
    rows = conn.execute(
        f"""SELECT r.id, r.encounter_id, r.status, r.proposed_priority, r.approved_priority, r.decision,
            r.requested_by, r.requested_at, r.decided_by, r.decided_at, r.action_type, e.chief_complaint,
            e.patient_id, p.given_name, p.family_name, ev.status AS evaluation_status, ev.urgent_flag
            FROM review_requests r JOIN encounters e ON e.id = r.encounter_id
            JOIN patients p ON p.id = e.patient_id
            JOIN protocol_evaluations ev ON ev.id = r.evaluation_id
            {where} ORDER BY ev.urgent_flag DESC, r.requested_at DESC LIMIT ?""", (*params, limit))
    return [dict(r) for r in rows]


def get_action_for_review(conn, review_id: str) -> dict | None:
    row = _row(conn.execute("SELECT * FROM workflow_actions WHERE review_id = ?", (review_id,)).fetchone())
    if row:
        row["payload"] = json.loads(row.pop("payload_json"))
        v = row.pop("verification_json")
        row["verification"] = json.loads(v) if v else None
    return row


def get_queue_entry(conn, encounter_id: str) -> dict | None:
    return _row(conn.execute("SELECT * FROM synthetic_queue WHERE encounter_id = ?", (encounter_id,)).fetchone())


def list_queue(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT q.*, e.patient_id, e.chief_complaint, e.arrived_at, p.given_name, p.family_name
           FROM synthetic_queue q JOIN encounters e ON e.id = q.encounter_id JOIN patients p ON p.id = e.patient_id
           WHERE e.status = 'open'
           ORDER BY q.priority_rank IS NULL, q.priority_rank, e.arrived_at""")]


def ensure_queue_entry(conn, encounter_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO synthetic_queue (encounter_id, updated_at) VALUES (?, ?)",
                 (encounter_id, utcnow()))


# --- Workflow runs ----------------------------------------------------------------------

def create_workflow_run(conn, thread_id: str, encounter_id: str, protocol_id: str, protocol_version: str,
                        started_by: str) -> None:
    now = utcnow()
    conn.execute(
        """INSERT INTO workflow_runs (thread_id, encounter_id, protocol_id, protocol_version, started_by, status,
           current_step, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (thread_id, encounter_id, protocol_id, protocol_version, started_by, "RUNNING", "queued", now, now),
    )


def update_workflow_run(conn, thread_id: str, **fields: Any) -> None:
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE workflow_runs SET {cols} WHERE thread_id = ?", (*fields.values(), thread_id))


def get_workflow_run(conn, thread_id: str) -> dict:
    row = _row(conn.execute("SELECT * FROM workflow_runs WHERE thread_id = ?", (thread_id,)).fetchone())
    if row is None:
        raise NotFound(f"workflow {thread_id} not found")
    return row


def list_workflow_runs(conn, encounter_id: str | None = None, limit: int = 50) -> list[dict]:
    if encounter_id:
        rows = conn.execute("SELECT * FROM workflow_runs WHERE encounter_id = ? ORDER BY created_at DESC LIMIT ?",
                            (encounter_id, limit))
    else:
        rows = conn.execute("SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def find_workflow_by_review(conn, review_id: str) -> dict | None:
    return _row(conn.execute("SELECT * FROM workflow_runs WHERE review_id = ?", (review_id,)).fetchone())
