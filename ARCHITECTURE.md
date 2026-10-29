# HospitalCare AI — Architecture (summary)

> Prototype · synthetic data only · not for clinical use. Full detail: [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md).

```text
React UI ──HTTP (session token)──► FastAPI ──► services (context · protocol · reviews) ──► SQLite (+ audit hash chain)
                                     │
                                     └─ LangGraph workflow (checkpointed, pauses for nurse review)
                                          ├─ MCP stdio ─► hospitalcare-ai server  (original)
                                          │                 get_patient_context · evaluate_triage_evidence · submit_nurse_review
                                          ├─ MCP stdio ─► @modelcontextprotocol/server-filesystem 2.0.1 (borrowed, read-only, reference/ only)
                                          └─ HTTP ─────► Ollama on 127.0.0.1 (phi4-mini) — narrative summary only
```

## Workflow

`validate → retrieve_context → retrieve_protocol → evaluate → summarize → create_review → ⏸ await_decision → execute_action → verify → finalize`

## Safety design in five rules

1. **Deterministic priority.** Only rules from a versioned protocol file are applied. Missing, unverified or conflicting evidence yields an unresolved status, never a guess. The shipped protocol is a labelled synthetic placeholder.
2. **Evidence comes from the database.** The evaluation tool doesn't accept caller-supplied values, and every criterion cites observation or symptom row IDs.
3. **Humans decide.** Only an authenticated session with `review:decide` can record a decision. The agent's delegation tokens can never carry that scope, and execution re-checks the database.
4. **Exactly-once, verified actions.** Each review gets one action row (enforced by a UNIQUE constraint). The synthetic queue is read back after every write, and a mismatch is reported as a failure.
5. **Local and auditable.** No hosted model APIs and no telemetry. Every tool call and decision lands in an append-only, hash-chained audit log.

## Repository layout

| Path | Contents |
|---|---|
| `backend/src/hospitalcare/` | Python package (API, agent, MCP server, services) |
| `backend/tests/` | pytest suite |
| `frontend/` | React + TypeScript + Vite UI |
| `mcp-filesystem/` | Pinned borrowed MCP server |
| `reference/protocols/` | Versioned protocol files; the only directory the filesystem server can reach |
| `docs/` | Project documentation and development memory |
