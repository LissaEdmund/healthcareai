"""Nurse-review lifecycle and the only code path that may change the synthetic queue (FR-012..FR-015).

State machine:
    PENDING --approve/override--> APPROVED --execute--> EXECUTED | EXECUTION_FAILED
    PENDING --reject--> REJECTED
    PENDING --request_clarification--> CLARIFICATION_REQUESTED
    EXECUTION_FAILED --execute (retry)--> EXECUTED | EXECUTION_FAILED
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Literal

from .. import audit
from .. import repositories as repo
from ..db import transaction, utcnow
from ..security import Principal, PermissionDenied, permissions_for, require
from .protocol import ProtocolError, load_protocol

ACTION_TYPE = "SET_SYNTHETIC_QUEUE_PRIORITY"
Decision = Literal["approve", "reject", "request_clarification", "override"]


class ReviewError(Exception):
    """Invalid request for the current review state (HTTP 409 / tool error)."""


class ActionFailure(Exception):
    """Raised by the queue writer; tests inject it to simulate failures."""


def create_review(conn: sqlite3.Connection, principal: Principal, *, encounter_id: str, evaluation_id: str,
                  idempotency_key: str, workflow_thread_id: str | None = None,
                  summary: dict | None = None) -> tuple[dict, bool]:
    """Create a PENDING review. Returns (review, created). Never touches the queue."""
    require(principal, "triage:run", scope="review:create", encounter_id=encounter_id)
    existing = repo.get_review_by_idempotency_key(conn, idempotency_key)
    if existing:
        if existing["encounter_id"] != encounter_id:
            raise ReviewError("idempotency key already used for a different encounter")
        audit.record(conn, "review_create_duplicate", outcome="info", principal=principal,
                     tool_name="submit_nurse_review", encounter_id=encounter_id, review_id=existing["id"],
                     approval_state=existing["status"], details={"idempotency_key": idempotency_key})
        return existing, False

    evaluation = repo.get_evaluation(conn, evaluation_id)
    if evaluation["encounter_id"] != encounter_id:
        raise ReviewError("evaluation does not belong to this encounter")
    encounter = repo.get_encounter(conn, encounter_id)
    if encounter["status"] != "open":
        raise ReviewError("encounter is closed")

    review_id = f"REV-{uuid.uuid4().hex[:10]}"
    now = utcnow()
    with transaction(conn):
        pending = conn.execute("SELECT id FROM review_requests WHERE encounter_id = ? AND status = 'PENDING'",
                               (encounter_id,)).fetchone()
        if pending:
            raise ReviewError(f"encounter already has a pending review ({pending['id']})")
        conn.execute(
            """INSERT INTO review_requests (id, encounter_id, evaluation_id, action_type, proposed_priority, status,
               idempotency_key, workflow_thread_id, summary_json, requested_by, requested_at, updated_at)
               VALUES (?,?,?,?,?,'PENDING',?,?,?,?,?,?)""",
            (review_id, encounter_id, evaluation_id, ACTION_TYPE, evaluation["proposed_priority"], idempotency_key,
             workflow_thread_id, json.dumps(summary) if summary else None, principal.user_id, now, now),
        )
        audit.record(conn, "review_created", outcome="success", principal=principal,
                     tool_name="submit_nurse_review", encounter_id=encounter_id, review_id=review_id,
                     workflow_thread_id=workflow_thread_id, action=ACTION_TYPE, approval_state="PENDING",
                     input_payload={"evaluation_id": evaluation_id, "idempotency_key": idempotency_key},
                     details={"proposed_priority": evaluation["proposed_priority"],
                              "evaluation_status": evaluation["status"]})
    return repo.get_review(conn, review_id), True


def record_decision(conn: sqlite3.Connection, principal: Principal, review_id: str, decision: Decision,
                    rationale: str, override_priority: str | None = None) -> dict:
    """Record a human decision. Only an authenticated *session* principal may decide (D-006)."""
    review = repo.get_review(conn, review_id)
    if principal.via != "session":
        audit.record(conn, "review_decision_denied", outcome="denied", principal=principal,
                     review_id=review_id, encounter_id=review["encounter_id"],
                     error="decisions require an authenticated user session")
        raise PermissionDenied("decisions require an authenticated user session, not an agent token")
    try:
        require(principal, "review:decide")
    except PermissionDenied as exc:
        audit.record(conn, "review_decision_denied", outcome="denied", principal=principal, review_id=review_id,
                     encounter_id=review["encounter_id"], error=str(exc))
        raise
    rationale = (rationale or "").strip()
    if len(rationale) < 3:
        raise ReviewError("a decision rationale is required")

    evaluation = repo.get_evaluation(conn, review["evaluation_id"])
    approved_priority = None
    if decision == "approve":
        if evaluation["status"] != "PROPOSED" or not review["proposed_priority"]:
            raise ReviewError("there is no proposed priority to approve; use override or reject")
        approved_priority = review["proposed_priority"]
    elif decision == "override":
        try:
            protocol = load_protocol(evaluation["protocol_id"], evaluation["protocol_version"]).protocol
        except ProtocolError as exc:
            raise ReviewError(f"cannot validate override priority: {exc}") from exc
        if override_priority not in {p.code for p in protocol.priority_levels}:
            raise ReviewError("override priority must be a level defined by the protocol")
        approved_priority = override_priority
    elif override_priority:
        raise ReviewError("override_priority is only valid with decision 'override'")

    new_status = {"approve": "APPROVED", "override": "APPROVED", "reject": "REJECTED",
                  "request_clarification": "CLARIFICATION_REQUESTED"}[decision]
    now = utcnow()
    with transaction(conn):
        cur = conn.execute(
            """UPDATE review_requests SET status=?, decision=?, rationale=?, approved_priority=?, decided_by=?,
               decided_at=?, updated_at=? WHERE id=? AND status='PENDING'""",
            (new_status, decision, rationale, approved_priority, principal.user_id, now, now, review_id),
        )
        if cur.rowcount != 1:
            current = conn.execute("SELECT status FROM review_requests WHERE id=?", (review_id,)).fetchone()
            raise ReviewError(f"review is not pending (status: {current['status']})")
        audit.record(conn, "review_decided", outcome="success", principal=principal, review_id=review_id,
                     encounter_id=review["encounter_id"], workflow_thread_id=review["workflow_thread_id"],
                     action=ACTION_TYPE, approval_state=new_status,
                     input_payload={"decision": decision, "rationale": rationale,
                                    "override_priority": override_priority},
                     details={"decision": decision, "approved_priority": approved_priority,
                              "proposed_priority": review["proposed_priority"]})
    return repo.get_review(conn, review_id)


def _write_queue(conn: sqlite3.Connection, encounter_id: str, priority: str, rank: int, action_id: str) -> None:
    conn.execute(
        """INSERT INTO synthetic_queue (encounter_id, priority, priority_rank, updated_at, updated_by_action_id)
           VALUES (?,?,?,?,?) ON CONFLICT(encounter_id) DO UPDATE SET priority=excluded.priority,
           priority_rank=excluded.priority_rank, updated_at=excluded.updated_at,
           updated_by_action_id=excluded.updated_by_action_id""",
        (encounter_id, priority, rank, utcnow(), action_id),
    )


# Indirection so tests can simulate a failing or misbehaving queue backend.
queue_writer = _write_queue


def execute_approved_action(conn: sqlite3.Connection, principal: Principal, review_id: str) -> dict[str, Any]:
    """Apply an APPROVED review's action exactly once and verify it.

    Returns {"status", "duplicate", "action", "review"}. Never reports success unless the
    synthetic queue read-back matches the approved priority.
    """
    review = repo.get_review(conn, review_id)
    encounter_id = review["encounter_id"]
    try:
        require(principal, "review:decide", scope="review:execute", encounter_id=encounter_id)
    except PermissionDenied as exc:
        audit.record(conn, "action_execution_denied", outcome="denied", principal=principal, review_id=review_id,
                     encounter_id=encounter_id, approval_state=review["status"], error=str(exc))
        raise

    existing = repo.get_action_for_review(conn, review_id)
    if review["status"] == "EXECUTED" and existing:
        audit.record(conn, "action_duplicate_suppressed", outcome="info", principal=principal, review_id=review_id,
                     encounter_id=encounter_id, action=ACTION_TYPE, approval_state="EXECUTED",
                     details={"action_id": existing["id"]})
        return {"status": "EXECUTED", "duplicate": True, "action": existing, "review": review}

    if review["status"] not in ("APPROVED", "EXECUTION_FAILED"):
        audit.record(conn, "action_execution_blocked", outcome="denied", principal=principal, review_id=review_id,
                     encounter_id=encounter_id, action=ACTION_TYPE, approval_state=review["status"],
                     error="review is not approved")
        raise ReviewError(f"action blocked: review status is {review['status']}, not APPROVED")
    if not review["decided_by"] or review["decision"] not in ("approve", "override"):
        raise ReviewError("action blocked: no recorded human approval")
    approver = conn.execute("SELECT role, active FROM users WHERE id = ?", (review["decided_by"],)).fetchone()
    if approver is None or not approver["active"] or "review:decide" not in permissions_for(approver["role"]):
        raise ReviewError("action blocked: approving user is not an active authorized reviewer")

    evaluation = repo.get_evaluation(conn, review["evaluation_id"])
    protocol = load_protocol(evaluation["protocol_id"], evaluation["protocol_version"]).protocol
    level = protocol.level(review["approved_priority"])
    payload = {"encounter_id": encounter_id, "priority": level.code, "priority_rank": level.rank,
               "queue": "SYNTHETIC (not connected to any hospital system)"}
    action_id = existing["id"] if existing else f"ACT-{uuid.uuid4().hex[:10]}"
    now = utcnow()

    # Claim the action row first: UNIQUE(review_id) makes a concurrent second execution lose here.
    try:
        with transaction(conn):
            if existing:  # retry after EXECUTION_FAILED
                conn.execute("UPDATE workflow_actions SET executed_by=?, executed_at=?, error=NULL WHERE id=?",
                             (principal.user_id, now, action_id))
            else:
                conn.execute(
                    """INSERT INTO workflow_actions (id, review_id, action_type, payload_json, executed_by,
                       executed_at, status) VALUES (?,?,?,?,?,?,'FAILED')""",
                    (action_id, review_id, ACTION_TYPE, json.dumps(payload), principal.user_id, now),
                )
    except sqlite3.IntegrityError:
        winner = repo.get_action_for_review(conn, review_id)
        audit.record(conn, "action_duplicate_suppressed", outcome="info", principal=principal, review_id=review_id,
                     encounter_id=encounter_id, action=ACTION_TYPE, approval_state=review["status"],
                     details={"action_id": winner["id"] if winner else None, "reason": "concurrent execution"})
        return {"status": repo.get_review(conn, review_id)["status"], "duplicate": True, "action": winner,
                "review": repo.get_review(conn, review_id)}

    error = None
    try:
        with transaction(conn):
            queue_writer(conn, encounter_id, level.code, level.rank, action_id)
    except (ActionFailure, sqlite3.Error) as exc:
        error = f"queue update failed: {exc}"

    # Verification: read back what is actually stored.
    entry = repo.get_queue_entry(conn, encounter_id)
    verified = error is None and entry is not None and entry["priority"] == level.code \
        and entry["updated_by_action_id"] == action_id
    verification = {"expected_priority": level.code, "observed_priority": entry["priority"] if entry else None,
                    "observed_action_id": entry["updated_by_action_id"] if entry else None, "verified_at": utcnow()}
    if error is None and not verified:
        error = "verification failed: synthetic queue does not reflect the approved priority"
    final_status = "EXECUTED" if verified else "EXECUTION_FAILED"

    with transaction(conn):
        conn.execute("UPDATE workflow_actions SET status=?, verified=?, verification_json=?, error=? WHERE id=?",
                     ("SUCCEEDED" if verified else "FAILED", int(verified), json.dumps(verification), error,
                      action_id))
        conn.execute("UPDATE review_requests SET status=?, updated_at=? WHERE id=?", (final_status, utcnow(),
                                                                                       review_id))
        audit.record(conn, "action_executed" if verified else "action_failed",
                     outcome="success" if verified else "failure", principal=principal, review_id=review_id,
                     encounter_id=encounter_id, workflow_thread_id=review["workflow_thread_id"], action=ACTION_TYPE,
                     approval_state=review["status"], input_payload=payload, output_payload=verification,
                     details={"action_id": action_id, "approved_by": review["decided_by"], "verified": verified},
                     error=error)
    return {"status": final_status, "duplicate": False, "action": repo.get_action_for_review(conn, review_id),
            "review": repo.get_review(conn, review_id), "error": error}
