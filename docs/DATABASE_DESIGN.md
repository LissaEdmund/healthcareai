# Database Design

SQLite (`data/hospitalcare.sqlite`, WAL mode, foreign keys on). Schema source of truth: `backend/src/hospitalcare/migrations/0001_initial.sql`. LangGraph checkpoints are in a separate file, `data/workflow_checkpoints.sqlite`, managed by `langgraph-checkpoint-sqlite`.

## Migration strategy

- Files `migrations/NNNN_description.sql` are applied in filename order by `db.migrate()`; applied versions are recorded in `schema_migrations(version, applied_at)`. Each migration runs in one transaction.
- `uv run hcai init-db` applies pending migrations; the API also migrates at startup.
- Never edit an applied migration; add a new file. The repository layer (`repositories.py`) isolates SQL so another database can be substituted later.

## Entities

| Table | Purpose | Key constraints |
|---|---|---|
| `users` | Staff accounts | `role` ∈ intake_clerk, nurse, clinician, auditor, admin; `password_hash` is scrypt |
| `sessions` | Login sessions | `token_hash` = SHA-256 of token (raw token never stored); `expires_at`, `revoked` |
| `patients` | Synthetic patients | `id LIKE 'SYN-P-%'`; `is_synthetic = 1` CHECK |
| `record_sources` | Availability of each record source per patient | UNIQUE(patient_id, source_type); status ∈ available, not_located, not_digitised, unavailable |
| `encounters` | Current and previous visits | `id LIKE 'SYN-E-%'`; `complaint_code`; `complaint_source`; `record_source`; status open/closed; index (patient_id, arrived_at) |
| `clinical_notes` | Verbatim documented items from encounters | category ∈ documented_assessment, documented_treatment, result, outcome, allergy, history; `source_type`, `source_ref`, `recorded_at` |
| `observations` | Vital signs and measurements | numeric or text value; `source_type`; `verification_status`; `status` active/superseded/entered_in_error; verifier and status-change audit columns |
| `symptoms` | Documented symptoms at an encounter | `present` 0/1; `source_type` patient_reported/clinician_observed |
| `protocol_evaluations` | Each evaluation result | protocol id/version/sha256/status; `status` enum; CHECK priority is NULL unless status = PROPOSED; full `result_json` |
| `review_requests` | Nurse review lifecycle | status enum; UNIQUE `idempotency_key`; partial UNIQUE index: one PENDING review per encounter; decision fields |
| `workflow_actions` | Executed actions | UNIQUE(`review_id`) — at most one action per review (idempotency); `verified`, `verification_json`, `error` |
| `synthetic_queue` | SYNTHETIC queue state | PK encounter_id; `updated_by_action_id` FK → workflow_actions (every priority traces to an action) |
| `workflow_runs` | Triage run tracking | thread_id PK; status; current_step; review_id; last_error |
| `audit_events` | Audit log | append-only (triggers abort UPDATE/DELETE); `prev_hash`/`hash` chain; actor, tool, encounter, review, thread, approval_state, outcome, input/output refs |

## Relationships

```text
patients 1─* encounters 1─* observations
                        1─* symptoms
                        1─* clinical_notes
                        1─* protocol_evaluations 1─* review_requests 1─0..1 workflow_actions
                        1─0..1 synthetic_queue ─→ workflow_actions
patients 1─* record_sources;  users 1─* sessions
```

## Indexes

`idx_encounters_patient`, `idx_notes_encounter`, `idx_obs_encounter`, `idx_symptoms_encounter`, `idx_review_status`, `uq_review_pending_per_encounter` (partial), `idx_workflow_encounter`, `idx_audit_ts`, `idx_audit_encounter`.

## Data lifecycle

- `uv run hcai seed --reset` deletes the local DB and checkpoints and reloads synthetic data.
- No retention policy is implemented in the prototype (see [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)).
