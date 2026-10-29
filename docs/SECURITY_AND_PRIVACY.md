# Security and Privacy

> The prototype holds **synthetic data only**. Real-world use requires facility authorization, privacy and legal review, clinical governance and an independent security assessment. No compliance with any legal or regulatory framework is claimed.

## Data protection

- All patient data is synthetic: IDs `SYN-P-`/`SYN-E-`, DB CHECK `is_synthetic = 1`, fictional surname "Mfano" (Swahili: "example"), UI banner on every page.
- Database, checkpoints and audit log are local SQLite files in `data/` (git-ignored).
- No telemetry, analytics, crash reporting or remote logging libraries are used. The only outbound HTTP call is to the local Ollama URL.

## Local model execution

- `HCAI_OLLAMA_URL` must resolve to a loopback address; startup (`hcai serve`, API lifespan) fails otherwise (tested).
- Ollama on the development machine is started bound to `127.0.0.1:11434` with models stored in `F:\ollama-models`.
- The model receives a reduced fact set and returns text only.

## Authentication and access control

- Passwords: scrypt (N=2^14, r=8, p=1, 16-byte salt).
- Sessions: 32-byte random tokens; only SHA-256 hashes stored; TTL `HCAI_SESSION_TTL_MINUTES` (default 480); logout revokes.
- Delegation tokens (agent → MCP): HMAC-SHA256 with `HCAI_SECRET_KEY`; payload = user, encounter, scopes, expiry, nonce; scopes limited to permissions the user holds; `review:decide` never delegable; current role re-checked on each use; deactivated users rejected.
- The HTTP API accepts only session tokens.
- Role permissions: [USER_ROLES_AND_PERMISSIONS.md](USER_ROLES_AND_PERMISSIONS.md). Every protected route and tool calls `require()`; denials are audited.
- Server-side validation of every request (Pydantic schemas + domain validation).

## Secrets management

- `.env` (git-ignored) holds `HCAI_SECRET_KEY` and `HCAI_DEMO_PASSWORD`; `.env.example` contains placeholders only.
- Startup refuses a missing/short/placeholder secret key outside test mode.
- Audit details and input/output references are computed after scrubbing keys named `password`, `token`, `actor_token`, `reviewer_token`, `authorization`, `secret`, `delegation_token` (tested).

## Logging and audit

- Append-only `audit_events` (DB triggers abort UPDATE and DELETE); SHA-256 hash chain verifiable at `GET /api/audit/verify`. The chain detects modification by anyone who bypasses the triggers (tested), but a party with full DB write access could rebuild the whole chain — anchoring the head hash externally is future work.
- Audit stores content hashes (`input_ref`, `output_ref`) rather than raw clinical payloads, plus small structured `details`.
- Failed logins record the username only.

## Filesystem restrictions

See [MCP_TOOLS.md](MCP_TOOLS.md#2-borrowed-server-modelcontextprotocolserver-filesystem): single allowed directory `reference/`, read-only allow-list, path validation, upstream guard.

## Data retention

Not implemented in the prototype. A deployment would need a facility-defined retention schedule for encounters, checkpoints and audit events, and a secure deletion procedure. `hcai seed --reset` wipes the local synthetic database.

## Known gaps

- No TLS (local loopback only). No rate limiting or account lockout on login.
- No CSRF exposure because tokens are sent in headers, not cookies; tokens live in `sessionStorage` (XSS would expose them; React escapes output, no `dangerouslySetInnerHTML` is used).
- Patient context is persisted in workflow checkpoints (local).
- No four-eyes approval (Q-03).
- Data at rest is not encrypted (OS-level disk encryption recommended).
