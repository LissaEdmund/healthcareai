# User Roles and Permissions

Source of truth: `ROLE_PERMISSIONS` in `backend/src/hospitalcare/security.py`.

## Permissions

| Permission | Meaning |
|---|---|
| `patient:read_basic` | Search patients; view demographics, encounter complaint, record-source availability |
| `patient:read_history` | View previous encounters, documented notes, current observations and symptoms |
| `patient:create` | Register synthetic patients |
| `encounter:create` | Open encounters |
| `observation:record` | Record observations (unverified) |
| `observation:verify` | Verify observations; record already-verified observations; supersede / mark entered-in-error |
| `symptom:record` | Record symptoms |
| `triage:run` | Start triage workflow runs; view runs and protocols |
| `review:read` | View the review queue and review details |
| `review:decide` | Approve, reject, request clarification, override; retry execution of approved actions |
| `queue:read` | View the synthetic queue |
| `audit:read` | View and verify the audit log |
| `system:read` | Reserved for system status (admin) |

## Roles

| Capability | intake_clerk | nurse | clinician | auditor | admin |
|---|:-:|:-:|:-:|:-:|:-:|
| View basic patient/encounter | ✔ | ✔ | ✔ | | |
| View history and observations | | ✔ | ✔ | | |
| Create patients | ✔ | ✔ | | | |
| Create encounters | ✔ | ✔ | | | |
| Record symptoms | ✔ | ✔ | ✔ | | |
| Record / verify observations | | ✔ | ✔ | | |
| Run triage workflow | | ✔ | ✔ | | |
| View reviews | | ✔ | ✔ | | |
| Decide reviews / retry action | | ✔ | ✔ | | |
| View synthetic queue | ✔ | ✔ | ✔ | | |
| View audit log | | | | ✔ | ✔ |
| Administer | | | | | system:read only |

The admin role deliberately has **no access to clinical content**. User administration endpoints are not implemented in the prototype; accounts are created by `hcai seed`.

## Agent (delegation) scopes

| Scope | Requires user permission |
|---|---|
| `context:read` | `patient:read_history` (tools also enforce `patient:read_basic`) |
| `triage:evaluate` | `triage:run` |
| `review:create` | `triage:run` |
| `review:read` | `review:read` |
| `review:execute` | `review:decide` |

`review:decide` is not a delegable scope: no agent can record a decision.

## Demo accounts (synthetic)

`intake.demo`, `nurse.demo` (Synthetic Nurse A), `nurse2.demo` (Synthetic Nurse B), `clinician.demo`, `auditor.demo`, `admin.demo` — all share `HCAI_DEMO_PASSWORD` from `.env`.

## Open question

Q-03: should the requester be prevented from approving their own review (four-eyes)? Currently allowed and fully audited.
