# Implementation Plan

Statuses: `PLANNED`, `IN_PROGRESS`, `DONE`, `BLOCKED`. Module IDs refer to [MODULES.md](MODULES.md).

| Phase | Scope | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| 0 | Repository inspection, documentation system, requirements, decisions, memory | — | Required docs exist and are consistent; open decisions listed | DONE |
| 1 | Foundation: config (M-01), DB + migrations (M-02), security (M-03), audit (M-04), FastAPI skeleton + health (M-12), pytest baseline | 0 | `hcai init-db` works; `/api/health` responds; tests run | DONE |
| 2 | Synthetic data + patient context (M-05, M-06) | 1 | Context returns provenance, missing items, conflicts, recurrence; authorization enforced | DONE |
| 3 | Original MCP server (M-09) + borrowed Filesystem MCP (M-10) | 2, 4 | 3 tools work over stdio and in-process; traversal and write attempts blocked | DONE |
| 4 | Protocol engine (M-07) | 1 | Deterministic evaluation; unresolved states; no priority without evidence | DONE |
| 5 | Reviews/actions (M-08), LLM (M-11), LangGraph agent (M-13) | 3, 4 | Graph pauses at review, resumes after authenticated decision, executes once, verifies, audits | DONE |
| 6 | Frontend (M-14) | 5 | Full demo through UI with role restrictions | DONE (browser walkthrough pending) |
| 7 | Full tests + evals (EVALS.md) | 6 | Actual results recorded | IN_PROGRESS (phi4-mini eval NOT RUN) |
| 8 | Demo script, README, ARCHITECTURE, licence review, secret scan | 7 | Another developer can run the demo from README | IN_PROGRESS (docs, demo script, licence review done; clean-install verification and first commit pending) |

## Blockers

- Local model server stopped after a memory-pressure event; the phi4-mini evaluation waits for a restart (user decision). Open questions that do not block the prototype are listed in [memory.md](memory.md#blocked-tasks-and-decisions-needed).
