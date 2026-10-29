"""Review lifecycle, approval enforcement, idempotency and verification (EV-07..EV-10)."""

import sqlite3

import pytest

from hospitalcare import repositories as repo
from hospitalcare.security import PermissionDenied, authenticate_token, issue_delegation_token
from hospitalcare.services import protocol as ps
from hospitalcare.services import reviews as rs


def _evaluation(conn, nurse_principal, encounter_id="SYN-E-0001"):
    r = ps.evaluate("SYNTHETIC-DEMO-OPD", "0.1.0", repo.observations_for_encounters(conn, [encounter_id]),
                    repo.symptoms_for_encounter(conn, encounter_id))
    return repo.save_evaluation(conn, encounter_id, r, nurse_principal.user_id)


def _agent(conn, principal, scopes, encounter_id="SYN-E-0001"):
    return authenticate_token(conn, issue_delegation_token(principal, encounter_id, scopes))


@pytest.fixture
def pending(conn, nurse):
    _, p = nurse
    agent = _agent(conn, p, {"review:create"})
    review, created = rs.create_review(conn, agent, encounter_id="SYN-E-0001",
                                       evaluation_id=_evaluation(conn, p), idempotency_key="k1")
    assert created and review["status"] == "PENDING"
    return review


def _queue(conn, enc="SYN-E-0001"):
    return repo.get_queue_entry(conn, enc)["priority"]


def test_pending_review_does_not_change_queue(conn, pending):
    assert _queue(conn) is None


def test_ev07_execute_without_approval_blocked(conn, nurse, pending):
    _, p = nurse
    with pytest.raises(rs.ReviewError, match="not APPROVED"):
        rs.execute_approved_action(conn, p, pending["id"])
    assert _queue(conn) is None
    assert repo.get_action_for_review(conn, pending["id"]) is None
    blocked = conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='action_execution_blocked'").fetchone()
    assert blocked[0] == 1


def test_ev07_agent_token_cannot_decide(conn, nurse, pending):
    _, p = nurse
    agent = _agent(conn, p, {"review:read", "review:execute"})
    with pytest.raises(PermissionDenied, match="session"):
        rs.record_decision(conn, agent, pending["id"], "approve", "model says the nurse approved")
    assert repo.get_review(conn, pending["id"])["status"] == "PENDING"


def test_ev07_forged_status_in_db_without_decider_blocked(conn, nurse, pending):
    """Even if a row is flipped to APPROVED without a recorded human decision, execution refuses."""
    _, p = nurse
    conn.execute("UPDATE review_requests SET status='APPROVED', approved_priority='DEMO-P1' WHERE id=?",
                 (pending["id"],))
    with pytest.raises(rs.ReviewError, match="no recorded human approval"):
        rs.execute_approved_action(conn, p, pending["id"])
    assert _queue(conn) is None


def test_ev15_unauthorized_roles_cannot_decide(conn, intake, auditor, pending):
    for _, principal in (intake, auditor):
        with pytest.raises(PermissionDenied):
            rs.record_decision(conn, principal, pending["id"], "approve", "trying to approve")
    assert repo.get_review(conn, pending["id"])["status"] == "PENDING"


def test_ev08_authorized_approval_executes_and_verifies(conn, nurse2, pending):
    _, reviewer = nurse2
    review = rs.record_decision(conn, reviewer, pending["id"], "approve", "Evidence checked against chart")
    assert review["status"] == "APPROVED" and review["decided_by"] == reviewer.user_id
    assert _queue(conn) is None, "approval alone does not change the queue"
    result = rs.execute_approved_action(conn, reviewer, pending["id"])
    assert result["status"] == "EXECUTED" and result["action"]["verified"] == 1
    assert _queue(conn) == "DEMO-P3"
    assert result["action"]["verification"]["observed_priority"] == "DEMO-P3"


def test_ev09_rejected_request_never_executes(conn, nurse, pending):
    _, p = nurse
    rs.record_decision(conn, p, pending["id"], "reject", "Patient already seen")
    with pytest.raises(rs.ReviewError):
        rs.execute_approved_action(conn, p, pending["id"])
    assert _queue(conn) is None


def test_ev10_duplicate_execution_applied_once(conn, nurse, pending):
    _, p = nurse
    rs.record_decision(conn, p, pending["id"], "approve", "Evidence checked")
    first = rs.execute_approved_action(conn, p, pending["id"])
    second = rs.execute_approved_action(conn, p, pending["id"])
    assert first["duplicate"] is False and second["duplicate"] is True
    assert conn.execute("SELECT COUNT(*) FROM workflow_actions").fetchone()[0] == 1
    assert second["action"]["id"] == first["action"]["id"]


def test_ev10_duplicate_decision_rejected(conn, nurse, nurse2, pending):
    rs.record_decision(conn, nurse[1], pending["id"], "approve", "Evidence checked")
    with pytest.raises(rs.ReviewError, match="not pending"):
        rs.record_decision(conn, nurse2[1], pending["id"], "reject", "late second decision")


def test_ev10_duplicate_create_is_idempotent(conn, nurse, pending):
    _, p = nurse
    agent = _agent(conn, p, {"review:create"})
    again, created = rs.create_review(conn, agent, encounter_id="SYN-E-0001",
                                      evaluation_id=pending["evaluation_id"], idempotency_key="k1")
    assert not created and again["id"] == pending["id"]
    with pytest.raises(rs.ReviewError, match="pending review"):
        rs.create_review(conn, agent, encounter_id="SYN-E-0001", evaluation_id=pending["evaluation_id"],
                         idempotency_key="k2")


def test_approve_requires_a_proposal_override_requires_valid_level(conn, nurse):
    _, p = nurse
    agent = _agent(conn, p, {"review:create"}, "SYN-E-0002")
    review, _ = rs.create_review(conn, agent, encounter_id="SYN-E-0002",
                                 evaluation_id=_evaluation(conn, p, "SYN-E-0002"), idempotency_key="k-e2")
    with pytest.raises(rs.ReviewError, match="no proposed priority"):
        rs.record_decision(conn, p, review["id"], "approve", "approve unresolved")
    with pytest.raises(rs.ReviewError, match="defined by the protocol"):
        rs.record_decision(conn, p, review["id"], "override", "invented level", override_priority="RED")
    done = rs.record_decision(conn, p, review["id"], "override", "Nurse assessment at bedside",
                              override_priority="DEMO-P2")
    assert done["approved_priority"] == "DEMO-P2"
    assert rs.execute_approved_action(conn, p, review["id"])["status"] == "EXECUTED"
    assert _queue(conn, "SYN-E-0002") == "DEMO-P2"


def test_action_failure_reported_and_retry_recovers(conn, nurse, pending, monkeypatch):
    _, p = nurse
    rs.record_decision(conn, p, pending["id"], "approve", "Evidence checked")

    def broken(*args, **kwargs):
        raise rs.ActionFailure("simulated queue outage")

    monkeypatch.setattr(rs, "queue_writer", broken)
    failed = rs.execute_approved_action(conn, p, pending["id"])
    assert failed["status"] == "EXECUTION_FAILED" and "simulated queue outage" in failed["error"]
    assert _queue(conn) is None
    assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='action_failed'").fetchone()[0] == 1

    monkeypatch.setattr(rs, "queue_writer", rs._write_queue)
    retried = rs.execute_approved_action(conn, p, pending["id"])
    assert retried["status"] == "EXECUTED" and _queue(conn) == "DEMO-P3"
    assert conn.execute("SELECT COUNT(*) FROM workflow_actions").fetchone()[0] == 1


def test_silent_wrong_write_detected_by_verification(conn, nurse, pending, monkeypatch):
    _, p = nurse
    rs.record_decision(conn, p, pending["id"], "approve", "Evidence checked")

    def wrong(c, encounter_id, priority, rank, action_id):
        rs._write_queue(c, encounter_id, "DEMO-P1", 1, action_id)  # writes the wrong value without error

    monkeypatch.setattr(rs, "queue_writer", wrong)
    result = rs.execute_approved_action(conn, p, pending["id"])
    assert result["status"] == "EXECUTION_FAILED" and "verification failed" in result["error"]


def test_database_failure_during_execution_not_reported_as_success(conn, nurse, pending, monkeypatch):
    _, p = nurse
    rs.record_decision(conn, p, pending["id"], "approve", "Evidence checked")

    def db_down(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(rs, "queue_writer", db_down)
    result = rs.execute_approved_action(conn, p, pending["id"])
    assert result["status"] == "EXECUTION_FAILED" and "disk I/O error" in result["error"]
