"""Authentication, delegation tokens, permissions and audit-chain integrity (FR-001, FR-002, FR-019, NFR-003)."""

import sqlite3

import pytest

from hospitalcare import audit
from hospitalcare.security import (AuthError, PermissionDenied, authenticate_token, hash_password,
                                   issue_delegation_token, require, revoke_session, verify_password)


def test_password_hash_roundtrip():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert "correct horse" not in h


def test_session_revocation(conn, nurse):
    token, _ = nurse
    assert authenticate_token(conn, token).username == "nurse.demo"
    revoke_session(conn, token)
    with pytest.raises(AuthError):
        authenticate_token(conn, token)


def test_session_expiry(conn, nurse):
    token, _ = nurse
    conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    with pytest.raises(AuthError, match="expired"):
        authenticate_token(conn, token)


def test_tokens_stored_hashed(conn, nurse):
    token, _ = nurse
    stored = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
    assert token not in stored


def test_delegation_token_never_carries_decide(conn, nurse):
    _, principal = nurse
    with pytest.raises(PermissionDenied):
        issue_delegation_token(principal, "SYN-E-0001", {"review:decide"})


def test_delegation_scopes_limited_to_user_permissions(conn, intake):
    _, principal = intake
    token = issue_delegation_token(principal, "SYN-E-0001", {"context:read", "triage:evaluate", "review:execute"})
    p = authenticate_token(conn, token)
    assert p.scopes == frozenset()  # intake clerk holds none of the underlying permissions


def test_delegation_tamper_and_encounter_binding(conn, nurse):
    _, principal = nurse
    token = issue_delegation_token(principal, "SYN-E-0001", {"context:read"})
    tampered = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
    with pytest.raises(AuthError):
        authenticate_token(conn, tampered)
    agent = authenticate_token(conn, token)
    require(agent, "patient:read_history", scope="context:read", encounter_id="SYN-E-0001")
    with pytest.raises(PermissionDenied, match="different encounter"):
        require(agent, "patient:read_history", scope="context:read", encounter_id="SYN-E-0002")
    with pytest.raises(PermissionDenied, match="scope"):
        require(agent, "triage:run", scope="triage:evaluate", encounter_id="SYN-E-0001")


def test_deactivated_user_delegation_rejected(conn, nurse):
    _, principal = nurse
    token = issue_delegation_token(principal, "SYN-E-0001", {"context:read"})
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (principal.user_id,))
    with pytest.raises(AuthError):
        authenticate_token(conn, token)


def test_audit_chain_valid_and_append_only(conn):
    audit.record(conn, "test_event", outcome="info", actor_type="system", details={"k": 1})
    assert audit.verify_chain(conn)["valid"]
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_events SET outcome = 'success'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_events")


def test_audit_chain_detects_tampering(conn):
    audit.record(conn, "test_event", outcome="info", actor_type="system")
    conn.execute("DROP TRIGGER audit_no_update")  # simulate an attacker with direct DB access
    conn.execute("UPDATE audit_events SET outcome = 'failure' WHERE seq = 1")
    result = audit.verify_chain(conn)
    assert not result["valid"] and result["broken_at_seq"] == 1


def test_audit_scrubs_secrets(conn):
    audit.record(conn, "test_event", outcome="info", actor_type="system",
                 details={"password": "hunter2", "actor_token": "dlg.abc", "nested": {"token": "x"}})
    row = conn.execute("SELECT details_json FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    assert "hunter2" not in row[0] and "dlg.abc" not in row[0] and "[REDACTED]" in row[0]
