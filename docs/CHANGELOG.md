# Changelog

## [0.1.0] — 2026-10-29 (unreleased prototype)

### Added
- Documentation system (`docs/`), requirements FR-001..FR-021 / NFR-001..NFR-010, decision log D-001..D-012.
- Backend: configuration, SQLite schema + migration runner, scrypt passwords, hashed sessions, HMAC delegation tokens, role permissions, hash-chained append-only audit log.
- Synthetic seed data (5 patients, 6 demo accounts) covering complete, missing, conflicting, escalation and new-patient scenarios.
- Patient-context service with provenance, missing-record, conflict and recurring-complaint detection.
- Protocol schema/loader/validator and deterministic evaluator; `SYNTHETIC-DEMO-OPD` v0.1.0 placeholder protocol (not for clinical use).
- Review lifecycle with idempotent, verified synthetic-queue action.
- Original MCP server `hospitalcare-ai` with `get_patient_context`, `evaluate_triage_evidence`, `submit_nurse_review`.
- Borrowed `@modelcontextprotocol/server-filesystem` 2.0.1 with read-only allow-list wrapper restricted to `reference/`.
- LangGraph workflow with interrupt-based nurse review, SQLite checkpoints and resume after restart.
- Local model summaries via Ollama with output guard.
- FastAPI HTTP API; `hcai` CLI.
- 108 automated tests.

### Changed
- 2026-10-28: guard extended to reject clinical-judgement words after the model described vitals as "stable" (EV-16).
- 2026-10-29: default model changed from `qwen2.5:3b` (Qwen Research Licence, non-commercial) to `phi4-mini` (MIT) — D-003.
- 2026-10-29: LangSmith tracing force-disabled at package import (privacy).

### Known issues
- EV-16 model misattribution between visits (unresolved). See [EVALS.md](EVALS.md).
