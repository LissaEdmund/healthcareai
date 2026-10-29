"""HospitalCare AI original MCP server.

Tools:
  get_patient_context       read-only, authorized patient context with provenance
  evaluate_triage_evidence  deterministic protocol evaluation; stores the evaluation record
  submit_nurse_review       review lifecycle: create / decide / execute / status

Every call requires `actor_token`: an agent delegation token (scoped, short-lived) or a
user session token. Every call is audited. Run with:  uv run hcai-mcp
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .. import audit
from .. import repositories as repo
from ..db import DatabaseError, get_conn
from ..security import AuthError, PermissionDenied, Principal, authenticate_token, require
from ..services import context as context_service
from ..services import protocol as protocol_service
from ..services import reviews as review_service

INSTRUCTIONS = (
    "HospitalCare AI tools operate on SYNTHETIC patient data. They never diagnose or prescribe. "
    "evaluate_triage_evidence only applies configured, versioned protocols. submit_nurse_review "
    "cannot record a decision with an agent token; decisions require an authenticated human session."
)


class PatientContextResult(BaseModel):
    context: dict[str, Any]


class EvaluationResult(BaseModel):
    evaluation_id: str | None = Field(description="Stored evaluation record; null if the encounter was invalid")
    result: dict[str, Any]


class ReviewResult(BaseModel):
    operation: str
    review: dict[str, Any] | None = None
    created: bool | None = None
    execution: dict[str, Any] | None = None
    queue_effect: str = Field(description="Plain statement of whether the synthetic queue changed")


@contextmanager
def _tool_call(tool: str, token: str, args: dict[str, Any], db_path=None) -> Iterator[tuple[sqlite3.Connection, Principal]]:
    """Authenticate, then audit the call's outcome. Converts domain errors into ToolErrors."""
    try:
        with get_conn(db_path) as conn:
            try:
                principal = authenticate_token(conn, token)
            except AuthError as exc:
                audit.record(conn, "tool_auth_failed", outcome="denied", tool_name=tool, input_payload=args,
                             encounter_id=args.get("encounter_id"), error=str(exc))
                raise ToolError(f"AUTHENTICATION_FAILED: {exc}") from exc
            try:
                yield conn, principal
            except PermissionDenied as exc:
                audit.record(conn, "access_denied", outcome="denied", principal=principal, tool_name=tool,
                             encounter_id=args.get("encounter_id"), review_id=args.get("review_id"),
                             input_payload=args, error=str(exc))
                raise ToolError(f"PERMISSION_DENIED: {exc}") from exc
            except repo.NotFound as exc:
                audit.record(conn, "tool_failed", outcome="failure", principal=principal, tool_name=tool,
                             encounter_id=args.get("encounter_id"), input_payload=args, error=str(exc))
                raise ToolError(f"NOT_FOUND: {exc}") from exc
            except (review_service.ReviewError, protocol_service.ProtocolError, ValueError) as exc:
                audit.record(conn, "tool_failed", outcome="failure", principal=principal, tool_name=tool,
                             encounter_id=args.get("encounter_id"), review_id=args.get("review_id"),
                             input_payload=args, error=str(exc))
                raise ToolError(f"INVALID_REQUEST: {exc}") from exc
    except (sqlite3.Error, DatabaseError) as exc:
        raise ToolError(f"DATABASE_UNAVAILABLE: {exc}") from exc


def build_server(db_path=None, protocols_dir=None) -> MCPServer:
    server = MCPServer("hospitalcare-ai", instructions=INSTRUCTIONS)

    @server.tool(
        description=(
            "Retrieve authorized, source-attributed context for a SYNTHETIC patient's current encounter: previous "
            "encounters, documented notes, observations, record-source availability, missing information, "
            "conflicts and recurring-complaint detection. Never invents data. Categories: demographics, "
            "current_encounter, history, record_sources (default all)."
        )
    )
    def get_patient_context(actor_token: str, patient_id: str, encounter_id: str,
                            categories: list[str] | None = None) -> PatientContextResult:
        args = {"patient_id": patient_id, "encounter_id": encounter_id, "categories": categories}
        with _tool_call("get_patient_context", actor_token, args, db_path) as (conn, principal):
            require(principal, "patient:read_basic", scope="context:read", encounter_id=encounter_id)
            ctx = context_service.build_patient_context(conn, principal, patient_id, encounter_id, categories)
            audit.record(conn, "tool_invoked", outcome="success", principal=principal,
                         tool_name="get_patient_context", encounter_id=encounter_id, input_payload=args,
                         output_payload=ctx, details={"categories_returned": ctx["categories_returned"],
                                                      "categories_withheld": ctx["categories_withheld"],
                                                      "conflicts": len(ctx["conflicts"]),
                                                      "missing_items": len(ctx["missing_information"])})
            return PatientContextResult(context=ctx)

    @server.tool(
        description=(
            "Evaluate the encounter's recorded, verified evidence against a configured, versioned triage protocol "
            "using deterministic rules. Evidence is read from the database (callers cannot supply values). Returns a "
            "proposed priority only when all required evidence is present, verified and consistent; otherwise an "
            "explicit unresolved status. A proposal is never a decision."
        )
    )
    def evaluate_triage_evidence(actor_token: str, encounter_id: str, protocol_id: str,
                                 protocol_version: str) -> EvaluationResult:
        args = {"encounter_id": encounter_id, "protocol_id": protocol_id, "protocol_version": protocol_version}
        with _tool_call("evaluate_triage_evidence", actor_token, args, db_path) as (conn, principal):
            require(principal, "triage:run", scope="triage:evaluate", encounter_id=encounter_id)
            repo.get_encounter(conn, encounter_id)
            observations = repo.observations_for_encounters(conn, [encounter_id])
            symptoms = repo.symptoms_for_encounter(conn, encounter_id)
            result = protocol_service.evaluate(protocol_id, protocol_version, observations, symptoms,
                                               directory=protocols_dir)
            evaluation_id = repo.save_evaluation(conn, encounter_id, result, principal.user_id)
            audit.record(conn, "tool_invoked", outcome="success", principal=principal,
                         tool_name="evaluate_triage_evidence", encounter_id=encounter_id, input_payload=args,
                         output_payload=result,
                         details={"evaluation_id": evaluation_id, "status": result["status"],
                                  "proposed_priority": result["proposed_priority"],
                                  "urgent_flag": result["urgent_flag"],
                                  "protocol_sha256": result["protocol_sha256"]})
            return EvaluationResult(evaluation_id=evaluation_id, result=result)

    @server.tool(
        description=(
            "Nurse-review lifecycle for a SYNTHETIC queue action. operation=create: open a PENDING review for an "
            "evaluation (idempotent by idempotency_key; never changes the queue). operation=decide: record a human "
            "decision (approve | reject | request_clarification | override) — requires a user SESSION token with "
            "review:decide; agent tokens are refused. operation=execute: apply an APPROVED review exactly once and "
            "verify the result. operation=status: read the review."
        )
    )
    def submit_nurse_review(
        actor_token: str,
        operation: Literal["create", "decide", "execute", "status"],
        encounter_id: str | None = None,
        evaluation_id: str | None = None,
        idempotency_key: str | None = None,
        review_id: str | None = None,
        decision: Literal["approve", "reject", "request_clarification", "override"] | None = None,
        rationale: str | None = None,
        override_priority: str | None = None,
        workflow_thread_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> ReviewResult:
        args = {"operation": operation, "encounter_id": encounter_id, "evaluation_id": evaluation_id,
                "idempotency_key": idempotency_key, "review_id": review_id, "decision": decision,
                "override_priority": override_priority, "workflow_thread_id": workflow_thread_id}
        with _tool_call("submit_nurse_review", actor_token, args, db_path) as (conn, principal):
            if operation == "create":
                if not (encounter_id and evaluation_id and idempotency_key):
                    raise ValueError("create requires encounter_id, evaluation_id and idempotency_key")
                review, created = review_service.create_review(
                    conn, principal, encounter_id=encounter_id, evaluation_id=evaluation_id,
                    idempotency_key=idempotency_key, workflow_thread_id=workflow_thread_id, summary=summary)
                return ReviewResult(operation=operation, review=review, created=created,
                                    queue_effect="none: pending reviews do not change the synthetic queue")
            if not review_id:
                raise ValueError(f"{operation} requires review_id")
            if operation == "decide":
                if decision is None:
                    raise ValueError("decide requires decision")
                review = review_service.record_decision(conn, principal, review_id, decision, rationale or "",
                                                        override_priority)
                return ReviewResult(operation=operation, review=review,
                                    queue_effect="none yet: an approved action is applied only by execute")
            if operation == "execute":
                execution = review_service.execute_approved_action(conn, principal, review_id)
                effect = ("unchanged (duplicate request suppressed)" if execution["duplicate"]
                          else "synthetic queue updated and verified" if execution["status"] == "EXECUTED"
                          else "update FAILED; see execution.error")
                return ReviewResult(operation=operation, review=execution["review"], execution=execution,
                                    queue_effect=effect)
            review = repo.get_review(conn, review_id)
            require(principal, "review:read", scope="review:read", encounter_id=review["encounter_id"])
            return ReviewResult(operation=operation, review=review, queue_effect="none (read-only)")

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
