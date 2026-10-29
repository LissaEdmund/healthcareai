# Project Overview — HospitalCare AI

> **Prototype status:** HospitalCare AI is a demonstration prototype that runs locally on **synthetic data only**. It is not a medical device, has not been clinically evaluated, and must not be used for real patient care.

## Purpose

HospitalCare AI is an agentic clinical *workflow* assistant for outpatient (OPD) triage. It helps an authorized nurse or clinician:

1. see the patient's **documented** history (previous visits, recorded complaints, observations, results and outcomes) without depending on the patient to reconstruct it from memory;
2. organize the current complaint, symptoms and observations together with their source and verification status;
3. compare **eligible, verified evidence** against an **explicitly configured, versioned triage protocol** using deterministic code;
4. receive an evidence-linked *proposal* that the nurse approves, rejects, overrides or sends back for clarification;
5. have an approved action executed (in this prototype, a clearly labelled **synthetic queue** update), verified and written to a tamper-evident audit log.

Workflow: **Patient arrival → Patient context retrieval → Current observations → Evidence-based triage evaluation → Human review and approval → Approved workflow action → Verification and audit logging.**

## Users

| User | Role in the prototype |
|---|---|
| Intake / records clerk | Registers synthetic patients and encounters, records the patient-reported complaint. |
| Triage nurse | Records and verifies observations, runs the triage workflow, reviews proposals. |
| Clinician | Same clinical permissions as the nurse; can review proposals. |
| Auditor | Read-only access to the audit log. |
| System administrator | Manages accounts and system status; no access to clinical content. |

See [USER_ROLES_AND_PERMISSIONS.md](USER_ROLES_AND_PERMISSIONS.md).

## Operating context

- Country: Tanzania. Department: outpatient. Records may be a mix of paper files (transcribed) and electronic records.
- Target facility: **configurable and not yet confirmed** (`HCAI_FACILITY_CODE`). No real hospital, partnership or facility protocol is assumed.
- Deployment: one local machine, local SQLite database, local open-weights model through Ollama.

## Problem statement

Relevant information is spread across paper files, electronic records and what the patient says. Under time pressure staff may not find it. Repeat visits for similar complaints are common; their documented history should be visible. A repeat visit is **not** evidence that earlier treatment failed, and the system never says so.

## Scope (prototype)

- Synthetic patients, encounters, observations, symptoms, historical notes and record-source availability.
- Patient-context retrieval with source/timestamp provenance, missing-record detection, conflict detection and recurring-complaint detection.
- Protocol loading/validation; deterministic evaluation only for protocols whose status permits evaluation.
- An original MCP server with three tools; a borrowed, read-only, directory-restricted Filesystem MCP server.
- A LangGraph workflow that pauses for authenticated human review and resumes afterwards.
- A local LLM that writes an optional narrative summary of already-retrieved facts, guarded against unsupported content.
- A React web UI, role-based access control, audit log with hash chaining, automated tests and evaluations.

## Expected outcomes

- A complete synthetic demonstration (under three minutes) showing MCP tool calls, evidence, the approval gate and the audit trail.
- Automated tests demonstrating that approvals cannot be bypassed, missing data is not invented and duplicate actions are not applied.

## Constraints

- No real patient data anywhere (fixtures, screenshots, source control).
- No hosted LLM APIs, telemetry or external logging; patient content stays on the machine.
- No invented clinical thresholds: the only shipped protocol is **`SYNTHETIC-DEMO-OPD`**, explicitly marked `synthetic_demo` and *not for clinical use* (see [DECISIONS.md](DECISIONS.md) D-002). It is evaluated only when `HCAI_DEMO_MODE=true`.
- Hardware observed on the development machine: 15.3 GB RAM, integrated AMD GPU (CPU inference), so a small (≈3B parameter) model is used.

## Non-goals

- Diagnosis, prescribing, medication recommendations, discharge or referral decisions.
- Integration with a real hospital queue, EMR, or HMIS (e.g. none is implemented or implied).
- Replacing the facility's emergency, triage or waiting-room reassessment process.
- Regulatory or legal compliance claims. Real-world use would require facility authorization, privacy/legal review, clinical governance and a security assessment.
