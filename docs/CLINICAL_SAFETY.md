# Clinical Safety

HospitalCare AI is a **workflow support tool, not an autonomous clinician**. The authorized nurse or clinician remains the decision-maker for every clinical action.

## Prohibited behaviour (enforced)

| Prohibition | How it is enforced |
|---|---|
| Diagnosing a patient | The model prompt forbids it; the output guard rejects summaries containing diagnosis language (`diagnos*`, "suggests … infection", etc.); no tool returns a diagnosis. Historical *documented* assessments are shown verbatim with source attribution only. |
| Prescribing / recommending medication | Guard rejects prescribing language and dose patterns (e.g. `500 mg`) not present in source facts; no tool produces medication content. |
| Claiming treatment failure from recurrence | Recurrence output is a fixed statement: "Recurrence of a documented complaint does not by itself indicate that previous treatment failed." Guard rejects "treatment failed"/"did not work" phrasing. |
| Inventing history, results, vital signs or observations | Context and evaluation read only database rows; the evaluation tool does not accept caller-supplied values (D-005); the guard rejects any number in a summary not present in the source facts. |
| Inventing thresholds or protocols | Rules come only from versioned protocol files; only `approved` protocols (or the labelled `synthetic_demo` protocol in demo mode) are evaluated. |
| Changing priority/queue autonomously | Queue writes happen only in `execute_approved_action`, which requires a database-recorded APPROVED decision by a user with `review:decide`. |
| Discharging/referring | No such action type exists. |
| Hiding uncertainty | Missing, unverified and conflicting evidence are always listed; unresolved states are explicit. |
| Treating missing documentation as absence | Missing records are reported as "not available in the records searched", never "did not happen". |
| Presenting synthetic as real | DB constraint `is_synthetic = 1`; `SYN-` identifiers; permanent UI banner. |
| Claiming effectiveness | Documentation states no clinical evaluation has been done. |

## Evidence eligibility

- Vital-sign criteria use only **active, verified** observations. Unverified values are reported as "present but unverified".
- Symptom criteria use symptoms documented at the current encounter (patient-reported, recorded by staff); they are labelled patient-reported.
- Two or more active, differing values for the same field → conflict → `CONFLICTING_EVIDENCE`; staff must verify one value and supersede the other.
- Historical records are contextual only and never satisfy a protocol criterion.

## Unresolved states

`PROTOCOL_UNAVAILABLE`, `PROTOCOL_NOT_APPROVED`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_EVIDENCE`, `NO_RULE_MATCHED`. None produce a priority. The reviewer may still record an override decision with rationale.

## Emergency and deterioration safeguards

- No emergency thresholds are invented. Protocol rules may be marked `escalation: true`; the only such rules shipped are **synthetic placeholders**.
- When an escalation rule matches (even if other evidence is missing), the result carries `urgent_flag = true` and the UI shows a prominent notice: "A configured escalation criterion is met. Direct this patient to immediate clinical review now using the facility's established process. Do not wait for this system."
- Deterministic evaluation runs **before** the model call, so the urgent flag never waits on the model.
- The system does not replace the facility's emergency, triage or waiting-room reassessment processes.

## Synthetic demo protocol

`SYNTHETIC-DEMO-OPD` (D-002) contains placeholder rules written only to exercise the software. Its thresholds are **not clinically validated** and must never be used for patient care. Using a real protocol requires a facility-approved document, a governance sign-off recorded in the protocol's `approval` block, and re-running the evaluation tests against it.

## Residual risks (prototype)

- A 3B local model may still produce misleading phrasing that passes the guard; summaries are labelled "AI-generated — verify against the sources" and are never used in evaluation.
- The conflict rule is strict equality per field; real practice may need tolerances defined by the facility.
- No four-eyes approval rule (open question Q-03).
