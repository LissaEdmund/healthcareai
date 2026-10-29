"""Append-only, hash-chained audit log.

Each event stores SHA-256 references to its input and output instead of raw
payloads, plus a small `details` dict. Secrets are stripped before storage.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .db import transaction, utcnow
from .security import Principal, sha256_hex

GENESIS_HASH = "0" * 64
_SECRET_KEYS = {"password", "token", "actor_token", "reviewer_token", "authorization", "secret", "delegation_token"}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in _SECRET_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def content_ref(payload: Any) -> str | None:
    """Stable SHA-256 reference to a payload (secrets removed first)."""
    if payload is None:
        return None
    return "sha256:" + sha256_hex(json.dumps(_scrub(payload), sort_keys=True, default=str))


_HASH_FIELDS = ("event_id", "ts", "actor_type", "actor_id", "actor_role", "event_type", "tool_name",
                "encounter_id", "review_id", "workflow_thread_id", "action", "approval_state", "outcome",
                "input_ref", "output_ref", "details_json", "error", "prev_hash")


def _event_hash(event: dict[str, Any]) -> str:
    return sha256_hex(json.dumps([event.get(f) for f in _HASH_FIELDS], default=str))


def record(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    outcome: str,
    principal: Principal | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    tool_name: str | None = None,
    encounter_id: str | None = None,
    review_id: str | None = None,
    workflow_thread_id: str | None = None,
    action: str | None = None,
    approval_state: str | None = None,
    input_payload: Any = None,
    output_payload: Any = None,
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> str:
    """Append an audit event and return its event_id."""
    if principal is not None:
        actor_type = actor_type or ("agent" if principal.via == "delegation" else "user")
        actor_id = actor_id or principal.user_id
    event = {
        "event_id": str(uuid.uuid4()),
        "ts": utcnow(),
        "actor_type": actor_type or "system",
        "actor_id": actor_id,
        "actor_role": principal.role if principal else None,
        "event_type": event_type,
        "tool_name": tool_name,
        "encounter_id": encounter_id,
        "review_id": review_id,
        "workflow_thread_id": workflow_thread_id,
        "action": action,
        "approval_state": approval_state,
        "outcome": outcome,
        "input_ref": content_ref(input_payload),
        "output_ref": content_ref(output_payload),
        "details_json": json.dumps(_scrub(details), sort_keys=True, default=str) if details else None,
        "error": error,
    }

    def _write() -> None:
        last = conn.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        event["prev_hash"] = last["hash"] if last else GENESIS_HASH
        event["hash"] = _event_hash(event)
        cols = ", ".join(event)
        conn.execute(f"INSERT INTO audit_events ({cols}) VALUES ({', '.join('?' * len(event))})",
                     tuple(event.values()))

    if conn.in_transaction:
        _write()
    else:
        with transaction(conn):
            _write()
    return event["event_id"]


def verify_chain(conn: sqlite3.Connection) -> dict[str, Any]:
    prev = GENESIS_HASH
    count = 0
    for row in conn.execute("SELECT * FROM audit_events ORDER BY seq"):
        event = dict(row)
        if event["prev_hash"] != prev or _event_hash(event) != event["hash"]:
            return {"valid": False, "events_checked": count, "broken_at_seq": event["seq"]}
        prev = event["hash"]
        count += 1
    return {"valid": True, "events_checked": count, "broken_at_seq": None}


def list_events(conn: sqlite3.Connection, *, limit: int = 200, event_type: str | None = None,
                encounter_id: str | None = None, review_id: str | None = None,
                workflow_thread_id: str | None = None) -> list[dict[str, Any]]:
    clauses, params = [], []
    for col, val in (("event_type", event_type), ("encounter_id", encounter_id),
                     ("review_id", review_id), ("workflow_thread_id", workflow_thread_id)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM audit_events {where} ORDER BY seq DESC LIMIT ?", (*params, limit))
    events = []
    for row in rows:
        event = dict(row)
        details_json = event.pop("details_json")
        event["details"] = json.loads(details_json) if details_json else None
        events.append(event)
    return events
