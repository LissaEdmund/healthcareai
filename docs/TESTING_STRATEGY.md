# Testing Strategy

Framework: pytest 9.2.0 + pytest-asyncio 1.4.1 (`asyncio_mode = auto`). Run from `backend/`:

```bash
uv run pytest                          # everything, including the real local model test
HCAI_SKIP_MODEL_TESTS=1 uv run pytest  # without Ollama
uv run pytest -m filesystem_mcp        # only borrowed-server tests (needs Node)
```

## Isolation

`tests/conftest.py` gives every test a fresh temporary data directory, a copy of `reference/`, a fixed test secret, `HCAI_MCP_TRANSPORT=inprocess` and `HCAI_LLM_ENABLED=false`, then migrates and seeds synthetic data. Tests never touch `data/` or `.env`.

## Layers

| Layer | File | What it covers |
|---|---|---|
| Unit — security/audit | `test_security_audit.py` | Password hashing, session expiry/revocation, hashed storage, delegation scopes, tampering, encounter binding, deactivated users, append-only triggers, hash-chain tamper detection, secret scrubbing |
| Unit — context | `test_context.py` | Provenance, missing data, conflicts (observations, allergy sources), recurrence wording, missing records, role-based withholding |
| Unit — protocol | `test_protocol.py` | Proposal traceability, determinism, insufficient/conflicting/unverified evidence, escalation flag, missing/draft/unsigned/invalid protocols, demo-mode gate, history not used |
| Unit — reviews | `test_reviews.py` | Approval enforcement, forged status, role denial, approval execution + verification, rejection, duplicates (execute, decide, create), override validation, injected queue failures, wrong-write detection, DB failure |
| MCP | `test_mcp.py` | Tool listing/schemas, in-process and **real stdio** calls, auth/scope denial + audit, agent cannot decide, DB/transport failure, filesystem restrictions (client and upstream) |
| Model | `test_llm.py` | Guard rules, unsupported numbers, model disabled/unreachable, loopback enforcement, **real qwen2.5:3b run**, known misattribution gap (strict xfail) |
| Workflow | `test_workflow.py` | Pause/resume, resume-without-decision, rejection, missing protocol, context failure, model failure, urgent ordering, concurrent pending review, restart resume, audit completeness |
| API / E2E | `test_api.py` | Health without patient data, login/logout, delegation tokens refused, role matrix, validation, synthetic IDs, full HTTP approval flow incl. duplicates and audit verification |
| Frontend | `npm run typecheck`, `npm run build` | Type safety and build; manual browser walkthrough (see EVALS) |

## Rules

- A test is reported as passed only after it has been executed; results are recorded in [EVALS.md](EVALS.md) and [memory.md](memory.md).
- Known gaps are encoded as `xfail(strict=True)` so they fail loudly when fixed.
- Security-relevant tests assert both the refusal and that no side effect happened (queue unchanged, no action row).
