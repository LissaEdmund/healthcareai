# MCP Servers and Tools

## 1. Original server: `hospitalcare-ai`

- Implementation: `backend/src/hospitalcare/mcp_server/server.py` (MCP Python SDK **2.3.0**, `MCPServer`).
- Run standalone: `uv run --directory backend hcai-mcp` (stdio). The agent spawns it as `python -m hospitalcare.mcp_server` when `HCAI_MCP_TRANSPORT=stdio`.
- Every tool takes `actor_token`: a **delegation token** (agent; scoped, encounter-bound, 15-minute) or a **session token** (human). Tokens are never written to the audit log (scrubbed).
- Error responses are MCP tool errors (`isError: true`) whose text starts with a code: `AUTHENTICATION_FAILED`, `PERMISSION_DENIED`, `NOT_FOUND`, `INVALID_REQUEST`, `DATABASE_UNAVAILABLE`.
- Every call writes audit events: `tool_invoked` (success; SHA-256 refs to input and output), `tool_auth_failed`, `access_denied`, `tool_failed`.

### `get_patient_context` (read-only)

| | |
|---|---|
| Input | `actor_token: str`, `patient_id: str`, `encounter_id: str`, `categories: list[str] \| null` (demographics, current_encounter, history, record_sources) |
| Output | `{context: {...}}` — see below |
| Permission | `patient:read_basic`; delegation scope `context:read`; token bound to `encounter_id`. History and current observations additionally need `patient:read_history`, otherwise listed in `categories_withheld` |
| Side effects | Audit event only |
| Errors | NOT_FOUND (unknown patient/encounter), INVALID_REQUEST (encounter belongs to another patient, unknown category), PERMISSION_DENIED |

Context fields: `data_label` ("SYNTHETIC — not a real patient"), `patient`, `encounter` (with `complaint_provenance`), `record_sources`, `current_observations[]` (id, code, label, value, unit, source_type, provenance, verification_status, status, source_ref, recorded_by, recorded_at), `current_symptoms[]`, `previous_encounters[]` (with verbatim `notes[]` and `observations[]`), `recurring_complaint{detected, complaint_code, lookback_days, prior_encounter_ids, statement}`, `missing_information[]{item, detail}`, `conflicts[]{field, scope, message, values[]}`, `categories_returned`, `categories_withheld`, `generated_at`.

Guarantees: only database rows; provenance on every item; patient-reported vs clinically recorded distinguished; missing records described as "not available in the records searched"; recurrence statement never claims treatment failure.

### `evaluate_triage_evidence` (writes an evaluation record)

| | |
|---|---|
| Input | `actor_token`, `encounter_id`, `protocol_id`, `protocol_version` — **no evidence values** (D-005) |
| Output | `{evaluation_id, result}`; `result` has `protocol_id`, `protocol_version`, `protocol_sha256`, `protocol_status`, `is_clinical_protocol`, `disclaimer`, `status`, `status_reason`, `proposed_priority`, `proposed_priority_label`, `proposed_priority_rank`, `urgent_flag`, `urgent_message`, `matched_rules[]{rule_id, priority, rank, description, escalation, criteria_met[]{field, op, value, evidence}}`, `undetermined_rules[]`, `evidence_used{}`, `missing_information[]`, `conflicts[]`, `historical_context_used:false`, `history_note`, `review_required:true`, `review_reason`, `evaluated_at` |
| Statuses | `PROPOSED`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_EVIDENCE`, `NO_RULE_MATCHED`, `PROTOCOL_UNAVAILABLE`, `PROTOCOL_NOT_APPROVED` |
| Permission | `triage:run`; scope `triage:evaluate`; encounter-bound |
| Side effects | Inserts `protocol_evaluations` row; audit event with status, priority, urgent flag, protocol hash |

### `submit_nurse_review` (consequential workflow action)

| Operation | Required args | Who | Effect |
|---|---|---|---|
| `create` | `encounter_id`, `evaluation_id`, `idempotency_key` (+ optional `workflow_thread_id`, `summary`) | `triage:run` / scope `review:create` | PENDING review. Same key → existing review returned (`created:false`). Second pending review for an encounter → INVALID_REQUEST. **Queue unchanged.** |
| `decide` | `review_id`, `decision`, `rationale` (+`override_priority` for override) | **session token only** with `review:decide` | Records the human decision; agent tokens → PERMISSION_DENIED (audited `review_decision_denied`). Queue unchanged. |
| `execute` | `review_id` | `review:decide` / scope `review:execute` | Requires DB status APPROVED (or EXECUTION_FAILED for retry), a recorded `approve`/`override` decision and an active approver with `review:decide`. Claims the single action row, writes the synthetic queue, reads it back, records `action_executed`/`action_failed`. Repeat → `duplicate:true`, nothing re-applied. |
| `status` | `review_id` | `review:read` / scope `review:read` | Read-only |

Output: `{operation, review, created?, execution?, queue_effect}` where `queue_effect` states in words whether the synthetic queue changed.

## 2. Borrowed server: `@modelcontextprotocol/server-filesystem`

| | |
|---|---|
| Source | https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem (official MCP organisation; repository active, last push 2026-10-27) |
| Version | **2.0.1**, pinned in `mcp-filesystem/package.json` + `package-lock.json`; requires Node ≥ 24 |
| Licence | Repository in MIT → Apache-2.0 transition; both permissive and compatible with this project |
| Purpose | Read approved reference material (versioned protocol files) for display and hash cross-check |
| Why not write our own | Path canonicalisation, symlink and traversal handling are subtle; the upstream implementation is tested and maintained |
| Launch | `node mcp-filesystem/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js <repo>/reference` (one allowed directory) |

Restrictions (implemented in `ReadOnlyFilesystemClient`, `backend/src/hospitalcare/mcp_clients.py`):

1. Tool allow-list: `read_text_file`, `list_directory`, `get_file_info`, `list_allowed_directories`. `write_file`, `edit_file`, `create_directory`, `move_file`, `read_media_file`, etc. are refused before reaching the server.
2. Paths must be relative, contain no `..`, no drive letters, no hidden segments (`.env`, `.git`), resolve inside `reference/`, and have an allowed suffix (`.yaml .yml .md .json .txt`).
3. The client does not advertise MCP Roots, so the allowed directory cannot be widened at runtime.
4. The upstream server independently rejects any path outside the allowed directory (tested by calling it directly).
5. `reference/` contains only protocols and reference text — never patient data, databases or secrets.

Limitations: the upstream server itself has no read-only mode; read-only is enforced by our client wrapper. Symlink-escape testing could not run on the development account (symlink creation not permitted) — see EVALS EV-14.

## Tests

`backend/tests/test_mcp.py` (tool listing/schemas, end-to-end in-process calls, real stdio subprocess, auth and scope failures, decide-with-agent-token refusal, DB failure, transport failure, filesystem path and tool restrictions, upstream guard).
