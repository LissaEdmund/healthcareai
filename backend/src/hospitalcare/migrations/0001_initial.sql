-- HospitalCare AI initial schema. All patient data is SYNTHETIC.

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('intake_clerk', 'nurse', 'clinician', 'auditor', 'admin')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
);

CREATE TABLE patients (
    id TEXT PRIMARY KEY CHECK (id LIKE 'SYN-P-%'),
    given_name TEXT NOT NULL,
    family_name TEXT NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('female', 'male', 'unknown')),
    birth_year INTEGER CHECK (birth_year BETWEEN 1900 AND 2100),
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1),
    created_by TEXT,
    created_at TEXT NOT NULL
);

-- Availability of each record source for a patient (paper file, electronic record, ...).
CREATE TABLE record_sources (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('electronic_record', 'paper_record')),
    status TEXT NOT NULL CHECK (status IN ('available', 'not_located', 'not_digitised', 'unavailable')),
    note TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (patient_id, source_type)
);

CREATE TABLE encounters (
    id TEXT PRIMARY KEY CHECK (id LIKE 'SYN-E-%'),
    patient_id TEXT NOT NULL REFERENCES patients(id),
    facility_code TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT 'OPD',
    arrived_at TEXT NOT NULL,
    complaint_code TEXT NOT NULL,
    chief_complaint TEXT NOT NULL,
    complaint_source TEXT NOT NULL DEFAULT 'patient_reported'
        CHECK (complaint_source IN ('patient_reported', 'electronic_record', 'paper_record_transcribed')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    record_source TEXT NOT NULL DEFAULT 'electronic_record'
        CHECK (record_source IN ('electronic_record', 'paper_record_transcribed')),
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_encounters_patient ON encounters(patient_id, arrived_at);

-- Documented clinical notes from previous or current encounters, kept verbatim with provenance.
CREATE TABLE clinical_notes (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    category TEXT NOT NULL CHECK (category IN
        ('documented_assessment', 'documented_treatment', 'result', 'outcome', 'allergy', 'history')),
    content TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN
        ('electronic_record', 'paper_record_transcribed', 'patient_reported')),
    source_ref TEXT,
    recorded_by TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX idx_notes_encounter ON clinical_notes(encounter_id);

CREATE TABLE observations (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    code TEXT NOT NULL,
    value_num REAL,
    value_text TEXT,
    unit TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN
        ('clinician_measured', 'device', 'patient_reported', 'paper_record_transcribed')),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('verified', 'unverified')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'entered_in_error')),
    source_ref TEXT,
    recorded_by TEXT,
    recorded_at TEXT NOT NULL,
    verified_by TEXT,
    verified_at TEXT,
    status_changed_by TEXT,
    status_reason TEXT,
    CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);
CREATE INDEX idx_obs_encounter ON observations(encounter_id, code);

CREATE TABLE symptoms (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    code TEXT NOT NULL,
    present INTEGER NOT NULL CHECK (present IN (0, 1)),
    source_type TEXT NOT NULL DEFAULT 'patient_reported'
        CHECK (source_type IN ('patient_reported', 'clinician_observed')),
    recorded_by TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX idx_symptoms_encounter ON symptoms(encounter_id, code);

CREATE TABLE protocol_evaluations (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    protocol_id TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    protocol_sha256 TEXT,
    protocol_status TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'INSUFFICIENT_EVIDENCE', 'CONFLICTING_EVIDENCE',
        'NO_RULE_MATCHED', 'PROTOCOL_UNAVAILABLE', 'PROTOCOL_NOT_APPROVED')),
    proposed_priority TEXT,
    urgent_flag INTEGER NOT NULL DEFAULT 0,
    result_json TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    CHECK (status = 'PROPOSED' OR proposed_priority IS NULL)
);

CREATE TABLE review_requests (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    evaluation_id TEXT NOT NULL REFERENCES protocol_evaluations(id),
    action_type TEXT NOT NULL CHECK (action_type IN ('SET_SYNTHETIC_QUEUE_PRIORITY')),
    proposed_priority TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CLARIFICATION_REQUESTED',
        'EXECUTED', 'EXECUTION_FAILED')),
    idempotency_key TEXT NOT NULL UNIQUE,
    workflow_thread_id TEXT,
    summary_json TEXT,
    requested_by TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    approved_priority TEXT,
    decided_by TEXT,
    decided_at TEXT,
    decision TEXT CHECK (decision IN ('approve', 'reject', 'request_clarification', 'override')),
    rationale TEXT,
    updated_at TEXT NOT NULL
);
-- At most one pending review per encounter.
CREATE UNIQUE INDEX uq_review_pending_per_encounter ON review_requests(encounter_id) WHERE status = 'PENDING';
CREATE INDEX idx_review_status ON review_requests(status);

CREATE TABLE workflow_actions (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL UNIQUE REFERENCES review_requests(id),
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    executed_by TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED')),
    verified INTEGER NOT NULL DEFAULT 0,
    verification_json TEXT,
    error TEXT
);

-- SYNTHETIC queue. Not connected to any real hospital system.
CREATE TABLE synthetic_queue (
    encounter_id TEXT PRIMARY KEY REFERENCES encounters(id),
    priority TEXT,
    priority_rank INTEGER,
    updated_at TEXT NOT NULL,
    updated_by_action_id TEXT REFERENCES workflow_actions(id)
);

CREATE TABLE workflow_runs (
    thread_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id),
    protocol_id TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    started_by TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step TEXT,
    review_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_workflow_encounter ON workflow_runs(encounter_id);

-- Append-only, hash-chained audit log.
CREATE TABLE audit_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    actor_id TEXT,
    actor_role TEXT,
    event_type TEXT NOT NULL,
    tool_name TEXT,
    encounter_id TEXT,
    review_id TEXT,
    workflow_thread_id TEXT,
    action TEXT,
    approval_state TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'denied', 'info')),
    input_ref TEXT,
    output_ref TEXT,
    details_json TEXT,
    error TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX idx_audit_ts ON audit_events(ts);
CREATE INDEX idx_audit_encounter ON audit_events(encounter_id);

CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
