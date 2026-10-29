# Agent Workflow

Implementation: `backend/src/hospitalcare/agent/graph.py` (LangGraph 1.2.18) and `agent/runner.py`.

## State machine

```text
START → validate_request ─fail→ finalize
            │ok
        retrieve_context ─fail (CONTEXT_UNAVAILABLE)→ finalize
            │
        retrieve_protocol (failure recorded, continues)
            │
        evaluate ─fail (EVALUATION_FAILED)→ finalize
            │
        summarize (model; never fails the run)
            │
        create_review ─fail (REVIEW_CREATION_FAILED)→ finalize
            │  status AWAITING_REVIEW
        await_decision ── interrupt() ── [paused; checkpointed]
            │ resumed → re-read review from DB via MCP status
            ├─ still PENDING → await_decision (pauses again)
            ├─ REJECTED → finalize (REJECTED_NO_ACTION)
            ├─ CLARIFICATION_REQUESTED → finalize
            └─ APPROVED → execute_action ─fail (ACTION_FAILED)→ finalize
                              │
                           verify → COMPLETED | ACTION_FAILED → finalize → END
```

State (`TriageState`): `thread_id, encounter_id, patient_id, protocol_id, protocol_version, started_by, status, context, protocol_document, evaluation_id, evaluation, summary, review_id, review, execution, recovery, errors[] (append), steps[] (append)`.

Each step appends `{step, tool, server, status, detail, started_at, finished_at}` to `steps`; the UI renders this as the visible tool-call timeline.

## Tool-selection boundaries (D-004)

| Node | Tool | Server |
|---|---|---|
| retrieve_context | `get_patient_context` | hospitalcare-ai |
| retrieve_protocol | `read_text_file` | filesystem (borrowed, read-only) |
| evaluate | `evaluate_triage_evidence` | hospitalcare-ai |
| summarize | Ollama `/api/chat` | local model (no tools) |
| create_review | `submit_nurse_review(create)` | hospitalcare-ai |
| await_decision | `submit_nurse_review(status)` | hospitalcare-ai |
| execute_action | `submit_nurse_review(execute)` | hospitalcare-ai |

The model cannot choose, add or skip tools; its output is not read by any other node.

## Approval checkpoint

- The graph pauses with `interrupt()` after creating the review. Nothing consequential happens while paused.
- Only `POST /api/reviews/{id}/decision` (authenticated session, `review:decide`) records a decision; it then resumes the graph as the reviewer.
- The resume payload (`{"resumed_by": user_id}`) is informational. The decision is read from the database; a resume without a decision simply pauses again (tested).
- Execution is re-validated server-side in `execute_approved_action`.

## Credentials

The runner mints delegation tokens and keeps them in `TOKEN_VAULT` (process memory) keyed by thread id — never in graph state or checkpoints (tested: no `dlg.` string in state). Start scopes: `context:read, triage:evaluate, review:create, review:read`. Resume scopes: `review:read, review:execute`. Tokens are removed in `finalize`.

## Persistence, retry and recovery

- Checkpoints: `AsyncSqliteSaver` at `data/workflow_checkpoints.sqlite`. A paused run can be resumed after a backend restart (tested).
- Idempotency: review `idempotency_key = "wf:<thread_id>"`; one action per review (DB UNIQUE).
- No automatic retries of tool calls (avoids duplicate side effects). Recovery paths are explicit: start a new run, or `POST /api/reviews/{id}/execute` for a failed approved action.
- Unhandled exceptions → run status `ERROR`, audit `workflow_error`.

## Termination conditions

`COMPLETED`, `REJECTED_NO_ACTION`, `CLARIFICATION_REQUESTED`, `ACTION_FAILED`, `VALIDATION_FAILED`, `CONTEXT_UNAVAILABLE`, `EVALUATION_FAILED`, `REVIEW_CREATION_FAILED`, `ERROR`. Non-terminal: `RUNNING`, `AWAITING_REVIEW`.
