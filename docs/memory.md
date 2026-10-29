# HospitalCare AI — Development Memory

## Project Snapshot
- Current phase: Phases 0–6 complete; Phase 7 partially complete (phi4-mini eval NOT RUN); Phase 8 docs done.
- Current working version: 0.1.0 (unreleased, git repository initialised, no commits yet)
- Last updated: 2026-10-29
- Overall status: Backend, MCP servers, agent and tests working (105 passed, 2 skipped, 1 strict-xfail). Frontend built (typecheck and build pass); browser walkthrough NOT RUN.
- Current development objective: run the phi4-mini evaluation and a browser walkthrough of the demo script.

## Implemented Modules
| Module | Status | Main Files | Tests | Notes |
|---|---|---|---|---|
| M-01 Configuration | TESTED | backend/src/hospitalcare/config.py, .env.example | test_llm.py (loopback), conftest | Repo-root `.env` |
| M-02 Persistence | TESTED | db.py, migrations/0001_initial.sql, repositories.py | all | `check_same_thread=False` for request-scoped conns |
| M-03 Security | TESTED | security.py | test_security_audit.py | `review:decide` never delegable |
| M-04 Audit | TESTED | audit.py | test_security_audit.py, test_workflow.py | Hash chain + triggers |
| M-05 Seed/catalog | TESTED | seed.py, catalog.py | via fixtures | 5 synthetic patients, 6 accounts |
| M-06 Context | TESTED | services/context.py | test_context.py | |
| M-07 Protocol engine | TESTED | services/protocol.py, reference/protocols/SYNTHETIC-DEMO-OPD_v0.1.0.yaml | test_protocol.py | Demo protocol only evaluable in demo mode |
| M-08 Reviews/actions | TESTED | services/reviews.py | test_reviews.py | claim-first action insert |
| M-09 Original MCP | TESTED | mcp_server/server.py | test_mcp.py | stdio + in-process |
| M-10 Borrowed FS MCP | TESTED (symlink BLOCKED) | mcp_clients.py, mcp-filesystem/package.json | test_mcp.py | v2.0.1 pinned |
| M-11 Local model | TESTED (qwen2.5:3b) / NOT RUN (phi4-mini) | llm.py | test_llm.py | EV-16 known failure |
| M-12 HTTP API | TESTED | api/app.py | test_api.py | |
| M-13 Agent | TESTED | agent/graph.py, agent/runner.py | test_workflow.py | |
| M-14 Frontend | IMPLEMENTED | frontend/src/{App,api,auth,hooks,format}.ts(x), components/*, pages/* | typecheck + build PASSED | npm audit: 2 moderate react-router 6 advisories |
| M-15 CLI | IMPLEMENTED | cli.py | manual | |

## Change History
### 2026-10-28 — Phase 0: repository inspection and documentation
- Module: documentation
- Reason: mandated documentation-first start; repository was empty.
- Files created: docs/PROJECT_OVERVIEW.md, REQUIREMENTS.md, DECISIONS.md, CLINICAL_SAFETY.md, IMPLEMENTATION_PLAN.md
- Files modified: none · Files deleted: none
- Behavior added or changed: none (docs)
- Database or API changes: none
- Security and clinical safety impact: defined prohibitions and the synthetic-protocol decision (D-002, confirmed by user)
- Tests executed: NOT RUN (no code)
- Documentation updated: as listed
- Known limitations: target facility and real protocol unknown
- Follow-up work: Phase 1

### 2026-10-28 — Phases 1–5: backend foundation, context, protocol, MCP, agent
- Module: M-01..M-13, M-15
- Reason: implement core workflow
- Files created: backend/pyproject.toml, backend/uv.lock, backend/src/hospitalcare/{__init__,config,db,security,audit,catalog,repositories,seed,cli,llm,mcp_clients}.py, migrations/0001_initial.sql, services/{context,protocol,reviews}.py, mcp_server/{server,__main__}.py, agent/{graph,runner}.py, api/app.py, backend/tests/{conftest,test_security_audit,test_context,test_protocol,test_reviews,test_mcp,test_llm,test_workflow,test_api}.py, reference/protocols/SYNTHETIC-DEMO-OPD_v0.1.0.yaml, mcp-filesystem/package.json (+lock), .gitignore, .env.example
- Files modified: none pre-existing · Files deleted: none
- Behavior added or changed: full triage workflow with MCP tools, approval gate, verified synthetic queue action, audit
- Database or API changes: initial schema 0001; API per API_REFERENCE.md
- Security and clinical safety impact: delegation tokens, session-only decisions, deterministic evaluation, loopback-only model
- Tests executed: `uv run pytest`
- Test results: PASSED — 106 passed, 1 skipped (symlink), 1 xfailed (EV-16). Fixes made during the run: test rationale too short (test bug), tamper test no-op (test bug), ExceptionGroup unwrapping (code bug), SQLite cross-thread connection (code bug).
- Documentation updated: SYSTEM_ARCHITECTURE, DATABASE_DESIGN, API_REFERENCE, MCP_TOOLS, AGENT_WORKFLOW, SECURITY_AND_PRIVACY, USER_ROLES_AND_PERMISSIONS, TESTING_STRATEGY, TROUBLESHOOTING, DEPLOYMENT
- Known limitations: EV-16 model misattribution; symlink test blocked
- Follow-up work: frontend

### 2026-10-28 — LLM guard: clinical-judgement rule
- Module: M-11 · Files modified: backend/src/hospitalcare/llm.py, backend/tests/test_llm.py
- Reason: qwen2.5:3b described vitals as "stable" and misattributed visit facts
- Behavior: guard rejects judgement words; prompt separates visits; strict xfail documents remaining misattribution gap
- Tests executed: test_llm.py — PASSED (12 passed, 1 xfailed)
- Safety impact: reduces unsupported clinical judgement in summaries

### 2026-10-29 — Model licence correction and privacy hardening
- Module: M-01, M-11 · Files modified: config.py, .env.example, backend/src/hospitalcare/__init__.py, docs/DECISIONS.md, THIRD_PARTY_LICENSES.md
- Reason: `ollama show qwen2.5:3b --license` = Qwen Research Licence (non-commercial); langsmith present transitively
- Behavior: default model → `phi4-mini` (MIT); LangSmith tracing env vars forced off at import
- Tests executed: full suite — PASSED (105 passed, 2 skipped: model offline + symlink, 1 xfailed)
- Known limitations: phi4-mini not yet evaluated (Ollama server was stopped by a memory-pressure event)

### 2026-10-29 — Phase 6: frontend
- Module: M-14 (built by a delegated agent, then verified by rerunning the build)
- Files created: frontend/{package.json,package-lock.json,.npmrc,tsconfig.json,vite.config.ts,index.html}, frontend/src/{main,App,api,auth,hooks,format}.ts(x), styles.css, components/{Banner,Layout,StateViews,Badge,Clinical,EvaluationView}.tsx, pages/{Login,Dashboard,Encounters,EncounterDetail,PatientHistory,Workflow,Reviews,ReviewDetail,Queue,Audit}Page.tsx; docs/UI_UX_SPECIFICATION.md
- Files modified: docs/MODULES.md, EVALS.md, IMPLEMENTATION_PLAN.md, memory.md
- Behavior: all screens; nav follows permissions; prototype banner everywhere
- Database or API changes: none
- Tests executed: `npm run typecheck`, `npm run build` — PASSED. API-level smoke test through the proxy — PASSED. It left one pending review; the DB was reseeded afterwards.
- Known limitations: see UI_UX_SPECIFICATION.md "Known UI limitations"; browser walkthrough NOT RUN

## Current Architecture
FastAPI (api/app.py) → services → SQLite. LangGraph graph runs as asyncio background task in the API process, checkpointed to data/workflow_checkpoints.sqlite; nodes call the original MCP server over stdio (subprocess per call) and the borrowed Filesystem MCP server over stdio (Node), and Ollama over loopback HTTP. React UI on Vite dev server proxies /api.

## Current Database and API State
- Migration 0001_initial only. Key invariants: `is_synthetic=1`, one PENDING review per encounter, UNIQUE action per review, append-only audit with hash chain.
- API contract: docs/API_REFERENCE.md. Decisions only via `POST /api/reviews/{id}/decision` (session). Workflows are async (202 + polling).

## Known Bugs and Limitations
- EV-16 (open): AI summary may misattribute facts between visits; guard cannot detect.
- phi4-mini model test NOT RUN.
- Symlink escape test BLOCKED (no privilege).
- Runs interrupted by process crash stay `RUNNING` (no auto re-drive).
- No login rate limiting; no TLS; no data retention policy.

## Pending Tasks
1. Browser walkthrough of docs/DEMO_SCRIPT.md (375 px, keyboard).
2. Start Ollama and run `uv run pytest -m model -s` with phi4-mini; record in EVALS.
3. First git commit (await user request).
4. Automated browser tests (Playwright) — optional.
5. Display-name lookup endpoint for user IDs; actor_role on login audit events; react-router v7 upgrade.

## Blocked Tasks and Decisions Needed
- Q-01: Target facility and its approved triage protocol (needed before any non-synthetic evaluation).
- Q-02: Clinical governance owner who signs `approval` blocks in protocol files.
- Q-03: Four-eyes rule — may the requester approve their own review?
- Q-04: Conflict tolerances per observation (currently strict inequality).
- Q-05: Retention schedule for encounters, checkpoints and audit events.

## Instructions for the Next Development Session
- Read this file, then docs/EVALS.md and docs/MODULES.md.
- Next task: phi4-mini evaluation (needs `ollama serve`; files: backend/src/hospitalcare/llm.py, backend/tests/test_llm.py). Acceptance: real-model test passes or the guard rejection is recorded honestly in EVALS.
- Then: address EV-16 with per-visit structured summaries (acceptance: test_ev16 xfail flips — remove the xfail marker).
