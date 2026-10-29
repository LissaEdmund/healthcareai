# Demonstration Script (≈ 3 minutes)

Preparation (before recording): `uv run hcai seed --reset`, start `ollama serve`, `uv run hcai serve`, `npm run dev`. Open two browser windows: window A logged in as `nurse.demo`, window B as `nurse2.demo`. Keep a third tab for `auditor.demo`.

| Time | Action | What to point out |
|---|---|---|
| 0:00 | Show the dashboard (window A) | "PROTOTYPE — SYNTHETIC DATA ONLY" banner, model status, nothing connected to a real hospital |
| 0:15 | Open encounter **SYN-E-0001** (Asha Mfano, headache) → *Patient history* | Two previous headache visits with sources (paper file p.4, EMR), timestamps, documented outcomes; recurring-complaint notice says recurrence does **not** imply treatment failure |
| 0:40 | Back to the encounter → *Start triage run* | Step timeline: `get_patient_context` (hospitalcare-ai MCP) → `read_text_file` (borrowed filesystem MCP, protocol sha256) → `evaluate_triage_evidence` → local model summary → `submit_nurse_review(create)` |
| 1:10 | Evaluation panel | "SYNTHETIC DEMO PROTOCOL — NOT A CLINICAL PRIORITY"; proposal DEMO-P3 with each criterion linked to observation IDs; review reason; "Awaiting nurse review — synthetic queue NOT changed" |
| 1:30 | Open the synthetic queue | SYN-E-0001 still has no priority while the review is pending |
| 1:40 | Window B (`nurse2.demo`) → Review queue → open review | "Signing as Synthetic Nurse B"; *Approve* with rationale "Evidence checked against chart" |
| 2:00 | Review page after the decision | Action executed, verification expected = observed `DEMO-P3`; synthetic queue updated |
| 2:15 | Optional: open **SYN-E-0004** and run triage | Urgent alert: configured escalation criterion (SpO2 88, placeholder rule) met even though temperature is missing; no priority proposed |
| 2:35 | Auditor tab → Audit log | `workflow_requested`, `tool_invoked` ×3, `model_summary`, `review_created`, `review_decided` (actor Nurse B), `action_executed`, `workflow_finished`; chain verification badge "valid" |
| 2:55 | Close | Nurse made the decision, every step was audited, all data is synthetic |

Bypass demonstration (optional, terminal): run `uv run pytest tests/test_reviews.py -k ev07 -v` to show approval bypass attempts being refused server-side.
