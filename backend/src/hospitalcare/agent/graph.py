"""LangGraph triage workflow (FR-016).

    validate_request -> retrieve_context -> retrieve_protocol -> evaluate -> summarize
      -> create_review -> await_decision (interrupt) -> execute_action -> verify -> finalize

Tool selection is fixed per node (D-004); the model is used only in `summarize`.
Failure at any consequential step routes to `finalize` with an explicit status and
never fabricates results. Delegation tokens live in `TOKEN_VAULT` (process memory),
never in graph state, so they are not written to checkpoints (D-006).
"""

from __future__ import annotations

import hashlib
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import audit
from .. import repositories as repo
from ..db import get_conn, utcnow
from ..llm import summarize_context
from ..mcp_clients import McpToolError, ReadOnlyFilesystemClient, call_original_tool
from ..services.protocol import ProtocolError, protocol_filename

TOKEN_VAULT: dict[str, str] = {}

TERMINAL_STATUSES = {"COMPLETED", "REJECTED_NO_ACTION", "CLARIFICATION_REQUESTED", "ACTION_FAILED",
                     "VALIDATION_FAILED", "CONTEXT_UNAVAILABLE", "EVALUATION_FAILED", "REVIEW_CREATION_FAILED"}

RECOVERY = {
    "VALIDATION_FAILED": "Check the encounter and start a new triage run.",
    "CONTEXT_UNAVAILABLE": "Patient context could not be retrieved; no history has been assumed. Continue with the "
                           "facility's manual triage process and retry the run when the service is available.",
    "EVALUATION_FAILED": "The protocol evaluation could not run. Triage manually using the facility's process; "
                         "retry the run after the error is resolved.",
    "REVIEW_CREATION_FAILED": "A review request could not be created (an open review may already exist). Check the "
                              "review queue.",
    "ACTION_FAILED": "The approved action was not applied or could not be verified. Use 'Retry action' on the "
                     "review; the queue has not been reported as updated.",
    "CLARIFICATION_REQUESTED": "Record or verify the requested information, then start a new triage run.",
    "REJECTED_NO_ACTION": "The proposal was rejected; nothing was changed.",
}


class TriageState(TypedDict, total=False):
    thread_id: str
    encounter_id: str
    patient_id: str
    protocol_id: str
    protocol_version: str
    started_by: str
    status: str
    context: dict[str, Any] | None
    protocol_document: dict[str, Any] | None
    evaluation_id: str | None
    evaluation: dict[str, Any] | None
    summary: dict[str, Any] | None
    review_id: str | None
    review: dict[str, Any] | None
    execution: dict[str, Any] | None
    recovery: str | None
    errors: Annotated[list[str], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]


def _thread(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


def _token(config: RunnableConfig) -> str:
    token = TOKEN_VAULT.get(_thread(config))
    if not token:
        raise McpToolError("agent", "no delegation token available for this workflow (restart or resume it)")
    return token


def _progress(state: TriageState, step: str, status: str = "RUNNING", **fields: Any) -> None:
    with get_conn() as conn:
        repo.update_workflow_run(conn, state["thread_id"], current_step=step, status=status, **fields)


def _step(name: str, status: str, *, tool: str | None = None, server: str | None = None, detail: str = "",
          started: str | None = None) -> dict[str, Any]:
    return {"step": name, "tool": tool, "server": server, "status": status, "detail": detail,
            "started_at": started or utcnow(), "finished_at": utcnow()}


def _audit_step(state: TriageState, event: str, outcome: str, **kw: Any) -> None:
    with get_conn() as conn:
        audit.record(conn, event, outcome=outcome, actor_type="agent", actor_id=state.get("started_by"),
                     encounter_id=state.get("encounter_id"), workflow_thread_id=state.get("thread_id"), **kw)


# --- Nodes ----------------------------------------------------------------------------------

async def validate_request(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "validate_request")
    try:
        with get_conn() as conn:
            enc = repo.get_encounter(conn, state["encounter_id"])
        if enc["status"] != "open":
            raise ValueError("encounter is not open")
        protocol_filename(state["protocol_id"], state["protocol_version"])
    except (repo.NotFound, ValueError, ProtocolError) as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="validate_request", error=str(exc))
        return {"status": "VALIDATION_FAILED", "errors": [str(exc)], "recovery": RECOVERY["VALIDATION_FAILED"],
                "steps": [_step("validate_request", "failed", detail=str(exc))]}
    _audit_step(state, "workflow_started", "success", action="validate_request",
                details={"protocol_id": state["protocol_id"], "protocol_version": state["protocol_version"]})
    return {"patient_id": enc["patient_id"], "status": "RUNNING",
            "steps": [_step("validate_request", "ok", detail="encounter open; request well-formed")]}


async def retrieve_context(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "retrieve_context")
    started = utcnow()
    try:
        payload = await call_original_tool("get_patient_context", {
            "actor_token": _token(config), "patient_id": state["patient_id"], "encounter_id": state["encounter_id"]})
    except McpToolError as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="retrieve_context", tool_name="get_patient_context",
                    error=str(exc))
        return {"status": "CONTEXT_UNAVAILABLE", "context": None, "errors": [f"Context retrieval failed: {exc}"],
                "recovery": RECOVERY["CONTEXT_UNAVAILABLE"],
                "steps": [_step("retrieve_context", "failed", tool="get_patient_context", server="hospitalcare-ai",
                                detail=str(exc), started=started)]}
    ctx = payload["context"]
    detail = (f"{len(ctx.get('previous_encounters', []))} previous encounters, "
              f"{len(ctx.get('missing_information', []))} missing items, {len(ctx.get('conflicts', []))} conflicts")
    return {"context": ctx, "steps": [_step("retrieve_context", "ok", tool="get_patient_context",
                                            server="hospitalcare-ai", detail=detail, started=started)]}


async def retrieve_protocol(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "retrieve_protocol")
    started = utcnow()
    rel = f"protocols/{protocol_filename(state['protocol_id'], state['protocol_version'])}"
    try:
        text = await ReadOnlyFilesystemClient().read_text(rel)
    except McpToolError as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="retrieve_protocol",
                    tool_name="filesystem.read_text_file", error=str(exc))
        doc = {"path": rel, "ok": False, "error": str(exc)}
        return {"protocol_document": doc, "errors": [f"Protocol document could not be read: {exc}"],
                "steps": [_step("retrieve_protocol", "failed", tool="read_text_file", server="filesystem (borrowed)",
                                detail=str(exc), started=started)]}
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _audit_step(state, "tool_invoked", "success", action="retrieve_protocol", tool_name="filesystem.read_text_file",
                output_payload={"sha256": sha}, details={"path": rel, "sha256": sha})
    return {"protocol_document": {"path": rel, "ok": True, "sha256": sha, "text": text},
            "steps": [_step("retrieve_protocol", "ok", tool="read_text_file", server="filesystem (borrowed)",
                            detail=f"{rel} sha256={sha[:12]}…", started=started)]}


async def evaluate(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "evaluate")
    started = utcnow()
    try:
        payload = await call_original_tool("evaluate_triage_evidence", {
            "actor_token": _token(config), "encounter_id": state["encounter_id"],
            "protocol_id": state["protocol_id"], "protocol_version": state["protocol_version"]})
    except McpToolError as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="evaluate", tool_name="evaluate_triage_evidence",
                    error=str(exc))
        return {"status": "EVALUATION_FAILED", "errors": [f"Evaluation failed: {exc}"],
                "recovery": RECOVERY["EVALUATION_FAILED"],
                "steps": [_step("evaluate", "failed", tool="evaluate_triage_evidence", server="hospitalcare-ai",
                                detail=str(exc), started=started)]}
    result = payload["result"]
    errors = []
    doc = state.get("protocol_document") or {}
    if doc.get("ok") and result.get("protocol_sha256") and doc["sha256"] != result["protocol_sha256"]:
        errors.append("Protocol document hash read via the filesystem server differs from the evaluated protocol.")
    detail = f"{result['status']}" + (f" → {result['proposed_priority']}" if result["proposed_priority"] else "")
    if result["urgent_flag"]:
        detail += " (ESCALATION CRITERION MET)"
    return {"evaluation_id": payload["evaluation_id"], "evaluation": result, "errors": errors,
            "steps": [_step("evaluate", "ok", tool="evaluate_triage_evidence", server="hospitalcare-ai",
                            detail=detail, started=started)]}


async def summarize(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "summarize")
    started = utcnow()
    summary = await summarize_context(state["context"] or {})
    _audit_step(state, "model_summary", "success" if summary["status"] == "GENERATED" else "failure",
                action="summarize", details={"status": summary["status"], "model": summary["model"],
                                             "violations": summary["violations"]},
                output_payload=summary.get("text"), error=summary.get("error"))
    return {"summary": summary,
            "steps": [_step("summarize", "ok" if summary["status"] == "GENERATED" else "degraded",
                            tool=f"ollama:{summary['model']}", server="local model",
                            detail=summary["status"] + (f": {summary['error']}" if summary.get("error") else ""),
                            started=started)]}


async def create_review(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "create_review")
    started = utcnow()
    summary = state.get("summary") or {}
    try:
        payload = await call_original_tool("submit_nurse_review", {
            "actor_token": _token(config), "operation": "create", "encounter_id": state["encounter_id"],
            "evaluation_id": state["evaluation_id"], "idempotency_key": f"wf:{state['thread_id']}",
            "workflow_thread_id": state["thread_id"],
            "summary": {"status": summary.get("status"), "text": summary.get("text"), "model": summary.get("model"),
                        "violations": summary.get("violations")}})
    except McpToolError as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="create_review", tool_name="submit_nurse_review",
                    error=str(exc))
        return {"status": "REVIEW_CREATION_FAILED", "errors": [str(exc)], "recovery": RECOVERY["REVIEW_CREATION_FAILED"],
                "steps": [_step("create_review", "failed", tool="submit_nurse_review(create)", server="hospitalcare-ai",
                                detail=str(exc), started=started)]}
    review = payload["review"]
    _progress(state, "await_decision", status="AWAITING_REVIEW", review_id=review["id"])
    return {"review_id": review["id"], "review": review, "status": "AWAITING_REVIEW",
            "steps": [_step("create_review", "ok", tool="submit_nurse_review(create)", server="hospitalcare-ai",
                            detail=f"{review['id']} PENDING — {payload['queue_effect']}", started=started)]}


async def await_decision(state: TriageState, config: RunnableConfig) -> dict:
    # Pauses the graph. The resume value is NOT trusted as a decision: the decision is re-read
    # from the database through the MCP status operation below.
    resume = interrupt({"review_id": state["review_id"], "message": "Awaiting authenticated nurse review"})
    _progress(state, "await_decision")
    started = utcnow()
    try:
        payload = await call_original_tool("submit_nurse_review", {
            "actor_token": _token(config), "operation": "status", "review_id": state["review_id"]})
    except McpToolError as exc:
        return {"errors": [str(exc)], "status": "AWAITING_REVIEW",
                "steps": [_step("await_decision", "failed", tool="submit_nurse_review(status)", detail=str(exc))]}
    review = payload["review"]
    status = {"APPROVED": "APPROVED", "REJECTED": "REJECTED_NO_ACTION",
              "CLARIFICATION_REQUESTED": "CLARIFICATION_REQUESTED", "EXECUTED": "APPROVED",
              "EXECUTION_FAILED": "APPROVED"}.get(review["status"], "AWAITING_REVIEW")
    note = f"resumed by {resume.get('resumed_by') if isinstance(resume, dict) else 'unknown'}"
    return {"review": review, "status": status,
            "recovery": RECOVERY.get(status),
            "steps": [_step("await_decision", "ok", tool="submit_nurse_review(status)", server="hospitalcare-ai",
                            detail=f"database review status {review['status']} ({review.get('decision')}); {note}",
                            started=started)]}


async def execute_action(state: TriageState, config: RunnableConfig) -> dict:
    _progress(state, "execute_action")
    started = utcnow()
    try:
        payload = await call_original_tool("submit_nurse_review", {
            "actor_token": _token(config), "operation": "execute", "review_id": state["review_id"]})
    except McpToolError as exc:
        _audit_step(state, "workflow_step_failed", "failure", action="execute_action",
                    tool_name="submit_nurse_review", review_id=state["review_id"], error=str(exc))
        return {"status": "ACTION_FAILED", "errors": [str(exc)], "recovery": RECOVERY["ACTION_FAILED"],
                "steps": [_step("execute_action", "failed", tool="submit_nurse_review(execute)",
                                server="hospitalcare-ai", detail=str(exc), started=started)]}
    return {"execution": payload["execution"], "review": payload["review"],
            "steps": [_step("execute_action", "ok", tool="submit_nurse_review(execute)", server="hospitalcare-ai",
                            detail=payload["queue_effect"], started=started)]}


async def verify(state: TriageState, config: RunnableConfig) -> dict:
    execution = state.get("execution") or {}
    action = execution.get("action") or {}
    ok = execution.get("status") == "EXECUTED" and bool(action.get("verified"))
    detail = (f"synthetic queue shows {action.get('verification', {}).get('observed_priority')}" if ok
              else f"not verified: {execution.get('error') or 'no successful execution'}")
    return {"status": "COMPLETED" if ok else "ACTION_FAILED",
            "recovery": None if ok else RECOVERY["ACTION_FAILED"],
            "steps": [_step("verify", "ok" if ok else "failed", detail=detail)]}


async def finalize(state: TriageState, config: RunnableConfig) -> dict:
    status = state.get("status", "UNKNOWN")
    _audit_step(state, "workflow_finished", "success" if status == "COMPLETED" else "info", action="finalize",
                review_id=state.get("review_id"), approval_state=(state.get("review") or {}).get("status"),
                details={"status": status, "errors": state.get("errors", [])})
    _progress(state, "finalize", status=status, last_error="; ".join(state.get("errors", [])) or None)
    TOKEN_VAULT.pop(state["thread_id"], None)
    return {"steps": [_step("finalize", "ok", detail=status)]}


# --- Routing ------------------------------------------------------------------------------

def _continue_unless_failed(next_node: str):
    def route(state: TriageState) -> str:
        return "finalize" if state.get("status") in TERMINAL_STATUSES else next_node
    return route


def _after_decision(state: TriageState) -> str:
    return {"APPROVED": "execute_action", "AWAITING_REVIEW": "await_decision"}.get(state.get("status"), "finalize")


def build_graph(checkpointer=None):
    g = StateGraph(TriageState)
    for name, fn in [("validate_request", validate_request), ("retrieve_context", retrieve_context),
                     ("retrieve_protocol", retrieve_protocol), ("evaluate", evaluate), ("summarize", summarize),
                     ("create_review", create_review), ("await_decision", await_decision),
                     ("execute_action", execute_action), ("verify", verify), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "validate_request")
    g.add_conditional_edges("validate_request", _continue_unless_failed("retrieve_context"))
    g.add_conditional_edges("retrieve_context", _continue_unless_failed("retrieve_protocol"))
    g.add_edge("retrieve_protocol", "evaluate")
    g.add_conditional_edges("evaluate", _continue_unless_failed("summarize"))
    g.add_edge("summarize", "create_review")
    g.add_conditional_edges("create_review", _continue_unless_failed("await_decision"))
    g.add_conditional_edges("await_decision", _after_decision)
    g.add_conditional_edges("execute_action", _continue_unless_failed("verify"))
    g.add_edge("verify", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
