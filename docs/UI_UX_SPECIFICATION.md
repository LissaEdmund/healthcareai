# UI / UX Specification

Implementation: `frontend/src/` (React 18.3.1, react-router-dom 6.30.6, Vite 6.4.5, TypeScript 5.9.3). The dev server runs on :5173 and proxies `/api` to :8000. No CDNs, web fonts, analytics or telemetry.

## Global

- **Banner on every page, including login:** "PROTOTYPE — SYNTHETIC DATA ONLY — NOT FOR CLINICAL USE — no real hospital system is connected" (`components/Banner.tsx`).
- **Navigation:** items appear according to `user.permissions` (`components/Layout.tsx`). The backend still enforces every permission.
- **Session:** the token is kept in `sessionStorage` (wrapped in try/catch). A 401 returns to login, and a reload restores the session via `/api/auth/me`.
- **Wording:** "Proposal", "Requires nurse review", "Decision by …" and "synthetic queue". The AI is never presented as the decision-maker.
- **States:** every data view has loading, empty and error states (`components/StateViews.tsx`). Errors show the server message. 422 `detail[]` errors are mapped to form fields; domain `{error}` 422s appear in a message box.

## Screens

| Route / page | Permission | Content |
|---|---|---|
| Login | — | Username and password form |
| Dashboard | any | Open-encounter count, review counts by status, urgent pending, model status, demo mode, recent events |
| Encounters / intake | `patient:read_basic`; forms need `patient:create` / `encounter:create` | Open-encounter list; synthetic patient form; encounter form with patient search and complaint codes |
| Encounter detail | `patient:read_basic` (+history for clinical data) | **Observations table:** value, unit, source, verification, status, recorder, time. Conflicts are shaded and labelled "⚠ Conflict". Rows have Verify and Supersede / Entered-in-error actions (a reason is required).<br>**Forms:** add an observation (the verified option only for verifiers); record symptoms as present or absent.<br>**Triage:** synthetic queue entry, a protocol select, *Start triage run*, and past runs. |
| Patient history | `patient:read_basic` | Previous encounters with verbatim notes (category, source, source ref, time) and Patient-reported / Clinically recorded badges. Also shows the recurring-complaint box (exact statement), missing information, conflicts, and each withheld category ("not shown — your role lacks permission"). |
| Triage run | `triage:run` | **Progress:** polls every 1.5 s and shows a step timeline (step, tool, server, status, detail). This is the visible record of MCP calls.<br>**Evaluation:** protocol id, version, short sha256, status and disclaimer, plus the "SYNTHETIC DEMO PROTOCOL — NOT A CLINICAL PRIORITY" label. Shows the proposal or unresolved status with matched rules and the evidence for each criterion, missing items, conflicts, the history note and the review reason.<br>**Urgent:** an urgent alert (`role="alert"`) at the top of the page.<br>**AI summary:** labelled "AI-generated summary — verify against the sources", or its unavailable/rejected status.<br>**Status:** "Awaiting nurse review — the synthetic queue has NOT been changed", or the recovery text for failed runs. |
| Review queue | `review:read` | Status tabs, urgent first, with badges |
| Review detail | `review:read`; decision needs `review:decide` | **Context:** the encounter and patient, the evaluation view and the summary.<br>**Decision form:** "Signing as …"; approve is disabled unless the evaluation is PROPOSED; override requires choosing a protocol level; rationale is required.<br>**After the decision:** shows the `queue_effect` and follows the status for up to 60 s. Shows the action's expected and observed priority and the queue entry, plus *Retry action* when EXECUTION_FAILED. |
| Synthetic queue | `queue:read` | The label "SYNTHETIC QUEUE — not connected to any hospital system" and the entries |
| Audit log | `audit:read` | Table (time, event, actor type/id/role, tool, encounter/review, approval state, outcome, error, shortened refs), event-type filter, row limit, chain-verification badge |

## Accessibility and responsiveness

- Semantic HTML with labelled controls and visible focus outlines. Status is always given as text plus colour.
- Wide tables scroll inside their own container, and the layout is intended to work at 375 px.
- **Not yet verified in a real browser:** keyboard-only walkthrough, screen-reader check and 375 px rendering (see EVALS gap 5).

## Known UI limitations (from frontend build report, 2026-10-29)

1. **Raw user IDs:** recorders, deciders and requesters appear as IDs like `USR-nurse2`, because there is no endpoint that resolves display names.
2. **Audit filter options:** the event-type filter options come from events already loaded.
3. **Approval-to-execution wait:** after approval the page polls the status. If the background workflow stalls, the user can use *Retry action*, since `/execute` accepts APPROVED reviews.
4. **Intake clerk symptoms:** clerks can record symptoms but can't see the list, because it requires `patient:read_history`.
5. **react-router-dom 6.30.6 advisories:** `npm audit` reports 2 moderate advisories, GHSA-wrjc-x8rr-h8h6 (open redirect) and GHSA-337j-9hxr-rhxg (SSR-only). The fix requires the breaking v7 upgrade, which is pending.
