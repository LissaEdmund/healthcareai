# Modules

Statuses: `PLANNED`, `IN_PROGRESS`, `IMPLEMENTED`, `TESTED`, `BLOCKED`. Paths are relative to `backend/src/hospitalcare/` unless stated.

| ID | Module | Responsibility | Depends on | Interface | Main files | Status |
|---|---|---|---|---|---|---|
| M-01 | Configuration | Env/.env settings, path resolution, runtime validation (secret, loopback model URL) | — | `get_settings()` | `config.py`, `/.env.example` | TESTED |
| M-02 | Persistence | SQLite connections, transactions, migrations, health | M-01 | `connect`, `transaction`, `migrate`, `check_health` | `db.py`, `migrations/0001_initial.sql`, `repositories.py` | TESTED |
| M-03 | Security | Passwords, sessions, delegation tokens, role permissions | M-02 | `authenticate_token`, `require`, `issue_delegation_token` | `security.py` | TESTED |
| M-04 | Audit | Append-only hash-chained events, scrubbing, verification | M-02, M-03 | `audit.record`, `verify_chain`, `list_events` | `audit.py` | TESTED |
| M-05 | Synthetic data & catalog | Coded vocabularies, data-entry ranges, demo seed | M-02 | `seed()`, `OBSERVATION_CODES` | `seed.py`, `catalog.py` | TESTED |
| M-06 | Patient context | Provenance-preserving context, missing/conflict/recurrence detection | M-02, M-03 | `build_patient_context` | `services/context.py` | TESTED |
| M-07 | Protocol engine | Protocol schema, loading, deterministic evaluation | M-01 | `load_protocol`, `evaluate`, `list_protocols` | `services/protocol.py`, `/reference/protocols/*.yaml` | TESTED |
| M-08 | Reviews & actions | Review lifecycle, decision recording, idempotent execution + verification, synthetic queue | M-04, M-07 | `create_review`, `record_decision`, `execute_approved_action` | `services/reviews.py` | TESTED |
| M-09 | Original MCP server | 3 tools over MCP (stdio) | M-06..M-08 | MCP tools | `mcp_server/server.py` | TESTED |
| M-10 | Borrowed Filesystem MCP | Pinned upstream server + read-only client wrapper | Node ≥ 24 | `ReadOnlyFilesystemClient` | `mcp_clients.py`, `/mcp-filesystem/package.json` | TESTED (symlink case BLOCKED) |
| M-11 | Local model | Ollama client, prompt, output guard | M-01 | `summarize_context`, `guard_summary`, `model_status` | `llm.py` | TESTED with qwen2.5:3b; phi4-mini NOT RUN; known gap EV-16 |
| M-12 | HTTP API | FastAPI routes, auth dependency, error mapping, health | M-03..M-08, M-13 | REST (see API_REFERENCE.md) | `api/app.py` | TESTED |
| M-13 | Agent workflow | LangGraph graph, runner, checkpoints, token vault | M-09..M-11 | `WorkflowRunner.start/resume/state` | `agent/graph.py`, `agent/runner.py` | TESTED |
| M-14 | Frontend | React UI for all screens | M-12 | Browser | `/frontend/src/` | IMPLEMENTED (typecheck + build pass; API-level smoke test; no automated browser tests) |
| M-15 | CLI | init-db, seed, check, serve | M-01, M-02, M-05 | `hcai` | `cli.py` | IMPLEMENTED (exercised manually) |
