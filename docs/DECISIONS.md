# Decision Log

Format: context → decision → alternatives → consequences. Decisions marked **(user)** were confirmed by the project owner.

## D-001 — Repository layout (2026-10-28)
- **Context:** The repository was empty. The master prompt shows a root named `HospitalCare-AI/`.
- **Decision:** The repository root is the existing `hospitalcareai/` directory. Source lives in `backend/` (Python package `hospitalcare`), `frontend/` (React), `mcp-filesystem/` (pinned borrowed MCP server), and `reference/` (the only directory exposed to the Filesystem MCP server).
- **Consequences:** Paths in documentation are relative to this root.

## D-002 — No real triage protocol; ship a synthetic demo protocol (2026-10-28) **(user)**
- **Context:** No approved clinical triage protocol has been supplied. Inventing thresholds is prohibited.
- **Decision:** Implement protocol loading, schema validation and deterministic evaluation. Ship exactly one protocol, `SYNTHETIC-DEMO-OPD` v0.1.0, with `status: synthetic_demo`, a non-clinical disclaimer, priority labels `DEMO-P1..P3` (deliberately not resembling any real triage scale's colours or names) and placeholder rules. The engine evaluates only `approved` protocols, or `synthetic_demo` protocols when `HCAI_DEMO_MODE=true`. Every output carries the protocol status and the UI labels demo results "NOT A CLINICAL PRIORITY".
- **Alternatives:** Disable evaluation entirely (demo would never show a proposal); wait for a user-supplied protocol.
- **Consequences:** Replacing the demo protocol with a facility-approved protocol is a data change (a new YAML file with `status: approved`) plus a clinical governance step; no code change.

## D-003 — Local model runtime and model (2026-10-28) **(user)**
- **Context:** 15.3 GB RAM, AMD integrated GPU (no CUDA), 13 GB free on C:, 42 GB on F:.
- **Decision:** Ollama 0.40.12, installed with winget; `OLLAMA_MODELS=F:\ollama-models`. Configurable through `HCAI_OLLAMA_MODEL`.
- **Revision (2026-10-29):** Development started with `qwen2.5:3b`, wrongly assumed to be Apache-2.0. `ollama show qwen2.5:3b --license` shows the **Qwen Research License** (non-commercial). The default was changed to **`phi4-mini`** (3.8B, Q4_K_M, MIT). `qwen2.5:1.5b` (Apache-2.0, ~1 GB) is the documented low-memory fallback. All model test results recorded before this date were obtained with qwen2.5:3b.
- **Alternatives:** `llama3.2:3b` (Llama community licence with use restrictions), 7–8B models (too slow and too memory-hungry on this CPU-only machine; the session already saw memory-pressure process termination).
- **Consequences:** Summaries take tens of seconds on CPU; the workflow runs in the background and the UI polls.

## D-004 — The LLM never computes priority and never selects tools (2026-10-28)
- **Decision:** Tool selection is fixed per graph node. The model receives already-retrieved facts and returns a narrative only. Priority comes solely from deterministic protocol evaluation.
- **Alternatives:** A ReAct-style tool-calling agent. Rejected: small local models are unreliable at tool calling, and it would allow the model to influence consequential actions.
- **Consequences:** The "agent" is an explicit state machine; the model is an optional, guarded component.

## D-005 — `evaluate_triage_evidence` reads evidence from the database, not from caller-supplied values (2026-10-28)
- **Decision:** The tool accepts `encounter_id`, `protocol_id`, `protocol_version`. Observations and symptoms are loaded server-side with provenance.
- **Consequences:** A caller (or model) cannot inject fabricated vital signs. Evidence references are real row IDs.

## D-006 — Approval comes only from an authenticated session; the agent uses scoped delegation tokens (2026-10-28)
- **Decision:** The graph calls MCP tools with a short-lived HMAC-signed delegation token (user, role, encounter, scopes, expiry) that **never** includes the `review:decide` scope. Decisions are recorded only through `POST /api/reviews/{id}/decision` (session token) or the MCP `decide` operation with a *session* token. Delegation tokens are held in process memory, never in graph state/checkpoints.
- **Consequences:** Text such as "the nurse approved" in model output or graph state has no effect. Execution re-checks the review row in the database.

## D-007 — Persistence: SQLite + versioned SQL migrations, no ORM (2026-10-28)
- **Decision:** `sqlite3` with a small migration runner (`hospitalcare/migrations/NNNN_*.sql`, `schema_migrations` table) and repository functions.
- **Alternatives:** SQLAlchemy + Alembic. Rejected for prototype simplicity; repositories keep replacement possible.

## D-008 — Borrowed MCP server: `@modelcontextprotocol/server-filesystem` 2.0.1 (2026-10-28)
- **Source:** https://github.com/modelcontextprotocol/servers (official MCP org; last push 2026-10-27; not archived). npm package 2.0.1, pinned in `mcp-filesystem/package.json` and `package-lock.json`.
- **Licence:** The repository is transitioning from MIT to Apache-2.0 (per its LICENSE file); both are compatible with this project's Apache-2.0 licence.
- **Why borrowed:** Path validation (symlink resolution, traversal checks) is security-sensitive and well tested upstream; rewriting it would add risk.
- **Restrictions:** Started with exactly one allowed directory (`reference/`); the client does not advertise MCP Roots, so the allow-list cannot be widened at runtime; the server has no read-only flag, so `ReadOnlyFilesystemClient` permits only `read_text_file`, `list_directory`, `get_file_info`, `list_allowed_directories` and additionally pre-validates paths and extensions. Patient data is never placed in `reference/`.

## D-009 — Frontend: React + TypeScript + Vite; licence Apache-2.0 (2026-10-28) **(user)**

## D-010 — Python 3.12 via uv (2026-10-28)
- **Context:** Python 3.14 is installed system-wide; some dependencies lag new CPython releases.
- **Decision:** `uv` manages an isolated Python 3.12 environment in `backend/.venv`; dependencies pinned in `pyproject.toml`/`uv.lock`.

## D-011 — Reviewers may override the proposed priority (2026-10-28)
- **Decision:** A reviewer can approve the proposal, reject it, request clarification, or **override** with any priority level defined in the protocol (rationale required). Override is the only way to set a priority when the evaluation is unresolved.
- **Open question (Q-03):** Whether facility governance requires a second reviewer (four-eyes) or forbids the requester approving their own request. Currently the same nurse may run the workflow and decide.

## D-012 — Workflow runs asynchronously (2026-10-28)
- **Decision:** `POST /api/workflows` returns 202 and the graph runs as a background task; the UI polls `GET /api/workflows/{thread_id}`. Consequence: CPU-bound model latency never blocks the UI.
