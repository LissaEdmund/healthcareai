"""LangGraph workflow: pause/resume, approval gate, failure handling, audit completeness (FR-016, EV-11..13)."""

import pytest

from hospitalcare import repositories as repo
from hospitalcare.agent.graph import TOKEN_VAULT
from hospitalcare.agent.runner import WorkflowRunner, checkpointer_context
from hospitalcare.services import reviews as rs


@pytest.fixture
async def runner(conn):
    async with checkpointer_context() as saver:
        yield WorkflowRunner(saver)


async def _start(runner, principal, enc="SYN-E-0001", protocol=("SYNTHETIC-DEMO-OPD", "0.1.0")):
    tid = runner.start(principal, enc, *protocol)
    await runner.wait(tid)
    return tid, await runner.state(tid)


async def test_full_workflow_pauses_then_completes_after_human_approval(conn, runner, nurse, nurse2):
    _, p = nurse
    tid, s = await _start(runner, p)
    assert s["paused_for_review"] and s["run"]["status"] == "AWAITING_REVIEW"
    steps = [x["step"] for x in s["state"]["steps"]]
    assert steps == ["validate_request", "retrieve_context", "retrieve_protocol", "evaluate", "summarize",
                     "create_review"]
    assert s["state"]["protocol_document"]["sha256"] == s["state"]["evaluation"]["protocol_sha256"]
    review_id = s["state"]["review_id"]
    assert repo.get_queue_entry(conn, "SYN-E-0001")["priority"] is None, "paused workflow changed nothing"
    assert "delegation" not in str(s["state"]) and "dlg." not in str(s["state"]), "no tokens in graph state"

    # A resume without any recorded decision does not execute anything; the run keeps waiting.
    runner.resume(nurse2[1], tid)
    await runner.wait(tid)
    s = await runner.state(tid)
    assert s["paused_for_review"] and repo.get_queue_entry(conn, "SYN-E-0001")["priority"] is None

    rs.record_decision(conn, nurse2[1], review_id, "approve", "Evidence matches chart")
    runner.resume(nurse2[1], tid)
    await runner.wait(tid)
    s = await runner.state(tid)
    assert s["run"]["status"] == "COMPLETED" and not s["next"]
    assert repo.get_queue_entry(conn, "SYN-E-0001")["priority"] == "DEMO-P3"
    assert tid not in TOKEN_VAULT


async def test_rejected_workflow_takes_no_action(conn, runner, nurse):
    _, p = nurse
    tid, s = await _start(runner, p)
    rs.record_decision(conn, p, s["state"]["review_id"], "reject", "Not appropriate")
    runner.resume(p, tid)
    await runner.wait(tid)
    s = await runner.state(tid)
    assert s["run"]["status"] == "REJECTED_NO_ACTION"
    assert repo.get_queue_entry(conn, "SYN-E-0001")["priority"] is None
    assert repo.get_action_for_review(conn, s["state"]["review_id"]) is None


async def test_ev05_missing_protocol_still_reaches_review_without_priority(conn, runner, nurse):
    _, p = nurse
    tid, s = await _start(runner, p, protocol=("NO-SUCH-PROTOCOL", "1.0.0"))
    ev = s["state"]["evaluation"]
    assert ev["status"] == "PROTOCOL_UNAVAILABLE" and ev["proposed_priority"] is None
    assert any("Protocol document could not be read" in e for e in s["state"]["errors"])
    review = repo.get_review(conn, s["state"]["review_id"])
    assert review["proposed_priority"] is None


async def test_ev11_context_failure_stops_without_fabrication(conn, runner, nurse, monkeypatch):
    from hospitalcare.agent import graph
    from hospitalcare.mcp_clients import McpToolError

    async def failing(tool, args):
        raise McpToolError(tool, "MCP server unavailable: simulated")

    monkeypatch.setattr(graph, "call_original_tool", failing)
    _, p = nurse
    tid, s = await _start(runner, p)
    assert s["run"]["status"] == "CONTEXT_UNAVAILABLE"
    assert s["state"]["context"] is None and "evaluation" not in s["state"]
    assert "no history has been assumed" in s["state"]["recovery"]
    assert conn.execute("SELECT COUNT(*) FROM review_requests").fetchone()[0] == 0


async def test_ev12_model_unavailable_workflow_continues_deterministically(conn, runner, nurse):
    _, p = nurse  # HCAI_LLM_ENABLED=false in tests
    tid, s = await _start(runner, p)
    assert s["state"]["summary"]["status"] == "MODEL_UNAVAILABLE" and s["state"]["summary"]["text"] is None
    assert s["state"]["evaluation"]["status"] == "PROPOSED"
    assert s["paused_for_review"]


async def test_urgent_case_flag_available_before_model(conn, runner, nurse):
    _, p = nurse
    tid, s = await _start(runner, p, enc="SYN-E-0004")
    ev = s["state"]["evaluation"]
    assert ev["urgent_flag"] and ev["status"] == "INSUFFICIENT_EVIDENCE"
    order = [x["step"] for x in s["state"]["steps"]]
    assert order.index("evaluate") < order.index("summarize")
    assert repo.list_reviews(conn, "PENDING")[0]["urgent_flag"] == 1  # urgent reviews sort first


async def test_second_run_while_review_pending_fails_safely(conn, runner, nurse):
    _, p = nurse
    await _start(runner, p)
    tid2, s2 = await _start(runner, p)
    assert s2["run"]["status"] == "REVIEW_CREATION_FAILED"
    assert conn.execute("SELECT COUNT(*) FROM review_requests WHERE status='PENDING'").fetchone()[0] == 1


async def test_resume_survives_runner_restart(conn, nurse):
    _, p = nurse
    async with checkpointer_context() as saver:
        r1 = WorkflowRunner(saver)
        tid, s = await _start(r1, p)
    rs.record_decision(conn, p, s["state"]["review_id"], "approve", "Approved after restart")
    async with checkpointer_context() as saver:
        r2 = WorkflowRunner(saver)  # fresh process state: new graph, empty token vault
        r2.resume(p, tid)
        await r2.wait(tid)
        assert (await r2.state(tid))["run"]["status"] == "COMPLETED"


async def test_ev13_audit_completeness(conn, runner, nurse, nurse2):
    _, p = nurse
    tid, s = await _start(runner, p)
    rs.record_decision(conn, nurse2[1], s["state"]["review_id"], "approve", "Evidence matches chart")
    runner.resume(nurse2[1], tid)
    await runner.wait(tid)
    rows = [dict(r) for r in conn.execute("SELECT * FROM audit_events WHERE encounter_id='SYN-E-0001' "
                                          "OR workflow_thread_id=? ORDER BY seq", (tid,))]
    types = [r["event_type"] for r in rows]
    for required in ("workflow_requested", "workflow_started", "tool_invoked", "model_summary", "review_created",
                     "review_decided", "action_executed", "workflow_finished"):
        assert required in types, f"missing audit event {required}"
    for r in rows:
        assert r["ts"] and r["actor_type"] and r["hash"] and r["prev_hash"]
    tool_events = [r for r in rows if r["event_type"] == "tool_invoked"]
    assert {r["tool_name"] for r in tool_events} >= {"get_patient_context", "evaluate_triage_evidence",
                                                     "filesystem.read_text_file"}
    assert all(r["output_ref"].startswith("sha256:") for r in tool_events)
    decided = next(r for r in rows if r["event_type"] == "review_decided")
    assert decided["actor_id"] == nurse2[1].user_id and decided["actor_type"] == "user"
    assert decided["approval_state"] == "APPROVED" and decided["input_ref"]
    executed = next(r for r in rows if r["event_type"] == "action_executed")
    assert executed["approval_state"] == "APPROVED" and executed["outcome"] == "success"
    from hospitalcare import audit

    assert audit.verify_chain(conn)["valid"]
