# System Architecture

This document describes the architecture **as implemented** (v0.1.0). The one-page summary is in [../ARCHITECTURE.md](../ARCHITECTURE.md).

## Components

```text
 Browser (React SPA, :5173)
   │  HTTPS-less local HTTP, Bearer session token
   ▼
 FastAPI backend (hospitalcare.api.app, :8000) ──────────────┐
   │  services: context, protocol, reviews; audit; security  │ SQLite: data/hospitalcare.sqlite
   │                                                         │   (patients, encounters, observations,
   │  WorkflowRunner (asyncio background tasks)              │    reviews, actions, synthetic queue,
   │    └─ LangGraph StateGraph ── AsyncSqliteSaver ─────────┤    audit_events hash chain)
   │         │                                               │ SQLite: data/workflow_checkpoints.sqlite
   │         ├─ MCP client ─stdio─► hospitalcare-ai MCP server (python -m hospitalcare.mcp_server)
   │         │                         tools: get_patient_context, evaluate_triage_evidence,
   │         │                                submit_nurse_review  ──► same SQLite DB
   │         ├─ MCP client ─stdio─► @modelcontextprotocol/server-filesystem 2.0.1 (Node)
   │         │     via ReadOnlyFilesystemClient, root = reference/ only
   │         └─ httpx ─────────────► Ollama on 127.0.0.1:11434 (qwen2.5:3b), summary only
```

| Layer | Implementation | Key files |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite; proxies `/api` to the backend | `frontend/src/` |
| HTTP API | FastAPI, request-scoped SQLite connections, error handlers mapping domain errors to 401/403/404/409/422/503 | `backend/src/hospitalcare/api/app.py` |
| Agent orchestration | LangGraph `StateGraph` with interrupt-based human checkpoint; `AsyncSqliteSaver` checkpoints | `agent/graph.py`, `agent/runner.py` |
| Original MCP server | MCP Python SDK 2.3.0 `MCPServer`; stdio transport in production, in-process in most tests | `mcp_server/server.py` |
| Borrowed MCP server | Official Filesystem server, pinned, read-only allow-list wrapper | `mcp_clients.py`, `mcp-filesystem/` |
| Domain services | Context building, protocol engine, review lifecycle | `services/*.py` |
| Persistence | `sqlite3`, versioned SQL migrations, repository functions | `db.py`, `migrations/`, `repositories.py` |
| Security | scrypt passwords, hashed session tokens, HMAC delegation tokens, role permissions | `security.py` |
| Audit | Append-only, SHA-256 hash-chained events, DB triggers block UPDATE/DELETE | `audit.py` |
| Local model | Ollama HTTP API, temperature 0, output guard | `llm.py` |

## Data flow for one triage run

1. Nurse clicks *Start triage run* → `POST /api/workflows` (permission `triage:run`). The runner mints a delegation token (scopes `context:read`, `triage:evaluate`, `review:create`, `review:read`, bound to the encounter, 15 min) kept in process memory, and starts the graph as a background task.
2. `retrieve_context` → MCP `get_patient_context` (stdio subprocess). The server authenticates the token against the DB, checks permission + scope + encounter binding, builds context from rows, audits `tool_invoked` with SHA-256 input/output references.
3. `retrieve_protocol` → Filesystem MCP `read_text_file` on `reference/protocols/<id>_v<version>.yaml`; the SHA-256 of the text is recorded.
4. `evaluate` → MCP `evaluate_triage_evidence`; the server loads the protocol itself, reads evidence from the DB, evaluates deterministically, stores a `protocol_evaluations` row. The graph compares the protocol hash with step 3.
5. `summarize` → Ollama (optional). Output is guarded; failures yield an explicit status.
6. `create_review` → MCP `submit_nurse_review(create)`; PENDING review; queue untouched. Graph status `AWAITING_REVIEW`.
7. `await_decision` → `interrupt()`. The graph is checkpointed and the task ends.
8. Reviewer submits `POST /api/reviews/{id}/decision` with their session token. The decision is written to the DB and audited; the runner resumes the graph with a new delegation token for the reviewer (scopes `review:read`, `review:execute`).
9. `await_decision` (resumed) re-reads the review status from the DB via MCP `status` — the resume payload is not trusted.
10. `execute_action` → MCP `submit_nurse_review(execute)`: re-validates APPROVED status, recorded decider and their permission; claims the action row (UNIQUE per review); writes the synthetic queue; reads it back; records `action_executed` or `action_failed`.
11. `verify` → checks the verified flag. `finalize` → audits `workflow_finished`, clears the token.

## Security boundaries

- **Browser ↔ API:** session bearer tokens; the API rejects delegation tokens.
- **Agent ↔ MCP server:** delegation tokens with explicit scopes; `review:decide` is never delegable; tokens are bound to one encounter; the user's current role is re-checked on every call.
- **Human approval:** recorded only by a session principal with `review:decide`, through the API (or the MCP `decide` operation with a session token).
- **Filesystem:** two independent checks (client allow-list + path validation; upstream allowed-directory check). Patient data is never in `reference/`.
- **Model:** loopback-only URL enforced at startup; the model sees a reduced fact set, has no tools, and its output never feeds evaluation or actions.

## Error handling

| Failure | Behaviour |
|---|---|
| Context tool fails | Run ends `CONTEXT_UNAVAILABLE`; no history assumed; recovery text shown |
| Protocol file unreadable via filesystem server | Error recorded; evaluation still runs (server is authoritative) and returns `PROTOCOL_UNAVAILABLE` if the protocol is truly absent |
| Evaluation tool fails | `EVALUATION_FAILED`; manual triage recovery text |
| Model unavailable / guard rejects | Summary status `MODEL_UNAVAILABLE` / `GUARD_REJECTED`; workflow continues |
| Review creation conflict | `REVIEW_CREATION_FAILED` (e.g. a pending review exists) |
| Action failure or verification mismatch | `EXECUTION_FAILED` / run `ACTION_FAILED`; retry via `POST /api/reviews/{id}/execute` |
| Unhandled exception in graph | Run marked `ERROR` with the message; audited `workflow_error` |
| Database unavailable | API 503 `DATABASE_UNAVAILABLE`; MCP `DATABASE_UNAVAILABLE` tool error |

## Known architectural limitations

- Background tasks live in the API process; a crash mid-step leaves the run `RUNNING` in `workflow_runs` (checkpoints allow resuming from the last completed node, but there is no automatic re-drive).
- A new MCP stdio subprocess is spawned per tool call (≈1 s overhead each); acceptable for the prototype.
- Patient context is stored in graph checkpoints (local SQLite) — subject to the same local-only protections as the main DB.
