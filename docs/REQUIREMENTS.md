# Requirements

Each requirement has a stable identifier. Evaluation scenarios that verify a requirement are listed in [EVALS.md](EVALS.md) (`EV-xx`). Status of implementation is tracked in [MODULES.md](MODULES.md).

## Functional requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-001 | Authenticate users with username and password; issue server-side session tokens. | Valid credentials return a token; invalid credentials return 401 without revealing which field was wrong; tokens expire (`HCAI_SESSION_TTL_MINUTES`) and can be revoked by logout. |
| FR-002 | Enforce role-based permissions on every protected API route and MCP tool. | A request lacking the required permission returns 403 (API) or a tool error (MCP) and writes an `access_denied` audit event. |
| FR-003 | Register synthetic patients and outpatient encounters. | Patient IDs are generated with the `SYN-P-` prefix; every patient row has `is_synthetic = 1` (DB CHECK constraint). |
| FR-004 | Record current observations and symptoms with source type, verification status, recorder and timestamp. | Each observation stores `source_type`, `verification_status`, `recorded_by`, `recorded_at`; values outside configured plausibility ranges are rejected with 422. |
| FR-005 | Verify observations, and mark observations as superseded or entered-in-error. | Only users with `observation:verify`; action audited; superseded values no longer count as eligible evidence. |
| FR-006 | Retrieve patient context (`get_patient_context`). | Returns previous encounters, documented notes, observations, record-source availability, missing items and conflicts; each item carries source and timestamp; patient-reported items are labelled separately from clinically recorded items. |
| FR-007 | Detect recurring complaints. | Prior encounters within `HCAI_RECURRENCE_LOOKBACK_DAYS` with the same complaint code are listed with their documented outcome, with the fixed statement that recurrence does not by itself indicate treatment failure. |
| FR-008 | Load and validate versioned triage protocols from the restricted reference directory. | Schema-invalid protocols are rejected; each evaluation records protocol id, version and SHA-256. |
| FR-009 | Evaluate evidence deterministically (`evaluate_triage_evidence`). | Same inputs → same output; every proposed priority lists matched criteria with evidence references (observation IDs, source, timestamp); missing, unverified and conflicting evidence produce an unresolved status instead of a priority. |
| FR-010 | Refuse evaluation without an evaluable protocol. | Missing protocol → `PROTOCOL_UNAVAILABLE`; status `draft`/`retired`, or `synthetic_demo` when demo mode is off → `PROTOCOL_NOT_APPROVED`; no priority is produced. |
| FR-011 | Flag configured escalation criteria. | If a rule marked `escalation: true` matches, `urgent_flag` is set even when the overall evaluation is unresolved, and the UI shows the evidence and directs to immediate clinical review. |
| FR-012 | Create nurse-review requests (`submit_nurse_review`, operation `create`). | Idempotency key prevents duplicate requests; at most one PENDING review per encounter; pending reviews never change the synthetic queue. |
| FR-013 | Record an authenticated reviewer's decision. | Only users with `review:decide` via an authenticated session; decision ∈ {approve, reject, request_clarification, override}; rationale required; an already-decided review returns 409. |
| FR-014 | Execute only approved actions. | Execution requires review status APPROVED recorded by an authorized reviewer; rejected/pending/clarification reviews cannot execute; execution is idempotent (one action per review). |
| FR-015 | Verify executed actions. | After execution the synthetic queue is read back and compared with the requested priority; mismatch → `EXECUTION_FAILED`, never reported as success. |
| FR-016 | Orchestrate the workflow as a stateful LangGraph graph that pauses for review and resumes. | Graph state is checkpointed in SQLite; the run can be resumed after a decision, including after a backend restart. |
| FR-017 | Generate an optional narrative summary with a local open-weights model. | The model receives only already-retrieved facts; output failing the guard (unsupported numbers, diagnosis/prescribing language) is discarded; model failure leaves deterministic functions working. |
| FR-018 | Retrieve protocol documents via the borrowed Filesystem MCP server. | Only read tools are callable; only the `reference/` directory is reachable; traversal and secret-file reads fail. |
| FR-019 | Audit every security- and workflow-relevant event. | Each event has actor, role, timestamp, event type, tool, encounter/review IDs, approval state, outcome, input/output SHA-256 references, error; events are hash-chained and chain verification is exposed. |
| FR-020 | Provide a web UI with dashboard, intake, history, triage review, review queue, synthetic queue and audit screens. | All screens enforce role restrictions; every page shows the synthetic-data/prototype banner. |
| FR-021 | Provide health and readiness checks. | `GET /api/health` reports database, model and filesystem-MCP status without requiring authentication and without patient content. |

## Non-functional requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| NFR-001 | Privacy: patient data stays local. | No outbound network calls except to the configured local Ollama URL; no telemetry libraries; startup warns if `HCAI_OLLAMA_URL` is not a loopback address. |
| NFR-002 | Secrets are not stored in source control. | `.env` is git-ignored; `.env.example` has placeholders only; `HCAI_SECRET_KEY` must be set (startup fails if left at the example value outside test mode). |
| NFR-003 | Logs exclude passwords, tokens and unnecessary clinical content. | Audit `details` never contain tokens or passwords (tested); tokens are stored as SHA-256 hashes. |
| NFR-004 | Traceability. | Every proposal can be traced to protocol version + hash and to specific observation rows. |
| NFR-005 | Reproducible local setup. | Documented commands initialize the DB, seed synthetic data, run tests and start both servers. |
| NFR-006 | Testability. | Each module has automated tests runnable with `uv run pytest`. |
| NFR-007 | Accessibility. | Semantic HTML, labelled form controls, keyboard-operable controls, status conveyed by text not colour alone. |
| NFR-008 | Responsiveness of the UI. | Long-running workflow steps run in the background; the UI polls and shows progress; urgent cases are never blocked on the model. |
| NFR-009 | Replaceable persistence. | Data access goes through repository functions in `hospitalcare/repositories.py`; no SQL in API or MCP layers. |
| NFR-010 | Model configurability. | Model name, URL and timeout are environment variables; no code change needed to switch models. |
