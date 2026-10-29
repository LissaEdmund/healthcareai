// Typed fetch client for the HospitalCare AI backend.
// All calls go to relative /api/... URLs (proxied to the backend by Vite in development).

export type Permission =
  | "patient:read_basic"
  | "patient:read_history"
  | "patient:create"
  | "encounter:create"
  | "observation:record"
  | "observation:verify"
  | "symptom:record"
  | "triage:run"
  | "review:read"
  | "review:decide"
  | "queue:read"
  | "audit:read"
  | "system:read";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: string;
  permissions: Permission[];
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface ModelStatus {
  available: boolean;
  model?: string;
  detail: string;
}

export interface AuditEventBrief {
  ts: string;
  event_type: string;
  actor_id: string | null;
  tool_name: string | null;
  outcome: string;
  encounter_id: string | null;
  review_id: string | null;
}

export interface Dashboard {
  notice: string;
  model: ModelStatus;
  demo_mode: boolean;
  encounters?: { open: number; total: number };
  reviews?: Record<string, number>;
  urgent_pending?: number;
  recent_events?: AuditEventBrief[];
}

export interface ObservationCodeMeta {
  label: string;
  unit: string | null;
  type: "number" | "text";
  range?: [number, number] | null;
  values?: string[];
}

export interface Catalog {
  observation_codes: Record<string, ObservationCodeMeta>;
  observation_sources: string[];
  symptom_codes: Record<string, string>;
  complaint_codes: Record<string, string>;
}

export interface Patient {
  id: string;
  given_name: string;
  family_name: string;
  sex: "female" | "male" | "unknown";
  birth_year: number | null;
  is_synthetic: number;
  created_by: string | null;
  created_at: string;
}

export interface Encounter {
  id: string;
  patient_id: string;
  facility_code: string;
  department: string;
  arrived_at: string;
  complaint_code: string;
  chief_complaint: string;
  complaint_source: string;
  status: "open" | "closed";
  record_source: string;
  created_by: string | null;
  created_at: string;
}

export interface EncounterListItem extends Encounter {
  given_name: string;
  family_name: string;
  synthetic_queue_priority: string | null;
  latest_review_status: string | null;
}

export interface Observation {
  id: string;
  encounter_id: string;
  code: string;
  value_num: number | null;
  value_text: string | null;
  unit: string | null;
  source_type: string;
  verification_status: "verified" | "unverified";
  status: "active" | "superseded" | "entered_in_error";
  source_ref: string | null;
  recorded_by: string | null;
  recorded_at: string;
  verified_by: string | null;
  verified_at: string | null;
  status_changed_by: string | null;
  status_reason: string | null;
}

export interface Symptom {
  id: string;
  encounter_id: string;
  code: string;
  present: number | boolean;
  source_type: string;
  recorded_by: string | null;
  recorded_at: string;
}

/** Observation as presented inside a patient context / conflict. */
export interface ContextObservation {
  id: string;
  code: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  source_type: string;
  provenance: "patient_reported" | "clinically_recorded";
  verification_status: string;
  status: string;
  source_ref: string | null;
  recorded_by: string | null;
  recorded_at: string;
}

export interface ConflictValue {
  id?: string;
  value: unknown;
  unit?: string | null;
  source_type?: string;
  source_ref?: string | null;
  recorded_at?: string;
  observation_id?: string;
  symptom_id?: string;
  verification_status?: string;
  label?: string;
  [key: string]: unknown;
}

export interface Conflict {
  field: string;
  scope?: string;
  message?: string;
  values: ConflictValue[];
}

export interface QueueEntry {
  encounter_id: string;
  priority: string | null;
  priority_rank: number | null;
  updated_at: string;
  updated_by_action_id: string | null;
}

export interface WorkflowRun {
  thread_id: string;
  encounter_id: string;
  protocol_id: string;
  protocol_version: string;
  started_by: string;
  status: string;
  current_step: string | null;
  review_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface EncounterDetail extends Encounter {
  patient: Patient;
  observations?: Observation[];
  symptoms?: Symptom[];
  conflicts?: Conflict[];
  synthetic_queue: QueueEntry | null;
  workflows: WorkflowRun[];
}

export interface MissingItem {
  item?: string;
  field?: string;
  detail?: string;
  reason?: string;
  observation_ids?: string[];
}

export interface HistoryNote {
  id: string;
  category: string;
  content: string;
  source_type: string;
  provenance: "patient_reported" | "clinically_recorded";
  source_ref: string | null;
  recorded_by: string | null;
  recorded_at: string;
}

export interface PreviousEncounter {
  id: string;
  arrived_at: string;
  complaint_code: string;
  chief_complaint: string;
  record_source: string;
  notes: HistoryNote[];
  observations: ContextObservation[];
}

export interface PatientContext {
  data_label: string;
  generated_at: string;
  patient_id: string;
  encounter_id: string;
  categories_returned: string[];
  categories_withheld: string[];
  missing_information: MissingItem[];
  conflicts: Conflict[];
  patient?: { id: string; display_name: string; sex: string; birth_year: number | null; is_synthetic: boolean };
  record_sources?: { source_type: string; status: string; note: string | null; updated_at: string }[];
  encounter?: {
    id: string;
    arrived_at: string;
    department: string;
    complaint_code: string;
    chief_complaint: string;
    complaint_source: string;
    complaint_provenance: string;
    status: string;
  };
  current_observations?: ContextObservation[];
  current_symptoms?: {
    id: string;
    code: string;
    label: string;
    present: boolean;
    source_type: string;
    provenance: string;
    recorded_by: string | null;
    recorded_at: string;
  }[];
  previous_encounters?: PreviousEncounter[];
  recurring_complaint?: {
    detected: boolean;
    complaint_code: string;
    lookback_days: number;
    prior_encounter_ids: string[];
    statement: string | null;
  };
}

export interface PriorityLevel {
  code: string;
  rank: number;
  label: string;
}

export interface Protocol {
  protocol_id?: string;
  version?: string;
  title?: string;
  status?: string;
  evaluable: boolean;
  sha256?: string;
  disclaimer?: string | null;
  valid: boolean;
  file: string;
  error?: string;
  priority_levels?: PriorityLevel[];
}

export interface Evidence {
  value: unknown;
  unit?: string | null;
  observation_id?: string;
  symptom_id?: string;
  source_type?: string;
  verification_status?: string;
  provenance?: string;
  recorded_by?: string | null;
  recorded_at?: string;
}

export interface CriterionMet {
  field: string;
  op: string;
  value: unknown;
  evidence: Evidence;
}

export interface MatchedRule {
  rule_id: string;
  priority: string;
  rank: number;
  description: string;
  escalation: boolean;
  match: string;
  criteria_met: CriterionMet[];
}

export interface EvaluationResult {
  protocol_id: string;
  protocol_version: string;
  protocol_sha256: string | null;
  protocol_status: string | null;
  protocol_title: string | null;
  is_clinical_protocol: boolean;
  disclaimer: string | null;
  status: string;
  status_reason: string;
  proposed_priority: string | null;
  proposed_priority_label: string | null;
  proposed_priority_rank: number | null;
  urgent_flag: boolean;
  urgent_message: string | null;
  matched_rules: MatchedRule[];
  undetermined_rules: { rule_id: string; priority: string; rank: number; missing_or_conflicting_fields: string[] }[];
  evidence_used: Record<string, Evidence>;
  missing_information: MissingItem[];
  conflicts: Conflict[];
  historical_context_used: boolean;
  history_note: string;
  review_required: boolean;
  review_reason: string;
  evaluated_at: string;
}

export interface Summary {
  status: string; // GENERATED | GUARD_REJECTED | MODEL_UNAVAILABLE
  text: string | null;
  model?: string | null;
  violations?: unknown[] | null;
  error?: string | null;
  label?: string;
}

export interface WorkflowStep {
  step: string;
  tool: string | null;
  server: string | null;
  status: string;
  detail: string;
  started_at: string;
  finished_at: string;
}

export interface Review {
  id: string;
  encounter_id: string;
  evaluation_id: string;
  action_type: string;
  proposed_priority: string | null;
  status: string;
  idempotency_key: string;
  workflow_thread_id: string | null;
  summary: Summary | null;
  requested_by: string;
  requested_at: string;
  approved_priority: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision: string | null;
  rationale: string | null;
  updated_at: string;
}

export interface WorkflowState {
  thread_id?: string;
  encounter_id?: string;
  patient_id?: string;
  protocol_id?: string;
  protocol_version?: string;
  started_by?: string;
  status?: string;
  context?: PatientContext | null;
  protocol_document?: { path: string; ok: boolean; sha256?: string; error?: string } | null;
  evaluation_id?: string | null;
  evaluation?: EvaluationResult | null;
  summary?: Summary | null;
  review_id?: string | null;
  review?: Review | null;
  execution?: Record<string, unknown> | null;
  recovery?: string | null;
  errors?: string[];
  steps?: WorkflowStep[];
}

export interface WorkflowDetail {
  run: WorkflowRun;
  state: WorkflowState;
  next: string[];
  paused_for_review: boolean;
  recovery: string | null;
}

export interface ReviewListItem {
  id: string;
  encounter_id: string;
  status: string;
  proposed_priority: string | null;
  approved_priority: string | null;
  decision: string | null;
  requested_by: string;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  action_type: string;
  chief_complaint: string;
  patient_id: string;
  given_name: string;
  family_name: string;
  evaluation_status: string;
  urgent_flag: number;
}

export interface EvaluationRow {
  id: string;
  encounter_id: string;
  protocol_id: string;
  protocol_version: string;
  protocol_sha256: string | null;
  protocol_status: string | null;
  status: string;
  proposed_priority: string | null;
  urgent_flag: number;
  created_by: string | null;
  created_at: string;
  result: EvaluationResult;
}

export interface WorkflowAction {
  id: string;
  review_id: string;
  action_type: string;
  payload: Record<string, unknown>;
  executed_by: string;
  executed_at: string;
  status: string;
  verified: number;
  verification: {
    expected_priority: string | null;
    observed_priority: string | null;
    observed_action_id?: string | null;
    verified_at?: string;
  } | null;
  error: string | null;
}

export interface ReviewDetail extends Review {
  evaluation: EvaluationRow;
  action: WorkflowAction | null;
  encounter: Encounter;
  patient: Patient;
  queue_entry: QueueEntry | null;
  priority_levels: PriorityLevel[];
}

export interface DecisionResponse {
  review: Review;
  workflow_resumed: string | null;
  queue_effect: string;
}

export interface ExecuteResponse {
  status: string;
  duplicate: boolean;
  action: WorkflowAction | null;
  review: Review;
  error?: string | null;
}

export interface QueueListEntry extends QueueEntry {
  patient_id: string;
  chief_complaint: string;
  arrived_at: string;
  given_name: string;
  family_name: string;
}

export interface QueueResponse {
  label: string;
  entries: QueueListEntry[];
}

export interface AuditEvent {
  seq: number;
  event_id: string;
  ts: string;
  actor_type: string;
  actor_id: string | null;
  actor_role: string | null;
  event_type: string;
  tool_name: string | null;
  encounter_id: string | null;
  review_id: string | null;
  workflow_thread_id: string | null;
  action: string | null;
  approval_state: string | null;
  outcome: string;
  input_ref: string | null;
  output_ref: string | null;
  details: Record<string, unknown> | null;
  error: string | null;
  prev_hash: string;
  hash: string;
}

export interface AuditVerify {
  valid: boolean;
  events_checked: number;
  broken_at_seq: number | null;
}

// --- Errors ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  code: string;
  /** Field-level messages from FastAPI 422 validation errors, keyed by field name. */
  fieldErrors: Record<string, string>;

  constructor(status: number, code: string, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

interface FastApiDetail {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON (e.g. proxy error page)
  }
  if (body && typeof body === "object") {
    const b = body as { error?: { code?: string; message?: string }; detail?: unknown };
    if (b.error && typeof b.error === "object") {
      return new ApiError(res.status, b.error.code ?? "ERROR", b.error.message ?? res.statusText);
    }
    if (Array.isArray(b.detail)) {
      const fieldErrors: Record<string, string> = {};
      const messages: string[] = [];
      for (const d of b.detail as FastApiDetail[]) {
        const loc = (d.loc ?? []).filter((p) => p !== "body" && p !== "query" && p !== "path");
        const field = loc.length ? String(loc[0]) : "_";
        const msg = d.msg ?? "invalid value";
        if (!fieldErrors[field]) fieldErrors[field] = msg;
        messages.push(loc.length ? `${loc.join(".")}: ${msg}` : msg);
      }
      return new ApiError(res.status, "VALIDATION_ERROR", messages.join("; ") || "Invalid request", fieldErrors);
    }
    if (typeof b.detail === "string") {
      return new ApiError(res.status, "ERROR", b.detail);
    }
  }
  if (res.status === 502 || res.status === 504) {
    return new ApiError(res.status, "BACKEND_UNREACHABLE", "The backend API is not reachable. Is it running on port 8000?");
  }
  return new ApiError(res.status, "HTTP_" + res.status, res.statusText || "Request failed");
}

// --- Token storage (sessionStorage, guarded) ----------------------------------------------

const TOKEN_KEY = "hcai.token";

export function loadToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable: token lives only in memory for this page load
  }
}

let memoryToken: string | null = loadToken();
let unauthorizedHandler: (() => void) | null = null;

export function setToken(token: string | null): void {
  memoryToken = token;
  saveToken(token);
}

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

// --- Core request -------------------------------------------------------------------------

export async function request<T>(method: "GET" | "POST", path: string, body?: unknown, opts: { skipAuthRedirect?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (memoryToken) headers["Authorization"] = `Bearer ${memoryToken}`;
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Network error: the backend API could not be reached.");
  }
  if (!res.ok) {
    const err = await parseError(res);
    if (res.status === 401 && !opts.skipAuthRedirect && unauthorizedHandler) unauthorizedHandler();
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>("GET", path);
const post = <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});

function qs(params: Record<string, string | number | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

// --- Endpoints ---------------------------------------------------------------------------

export const api = {
  login: (username: string, password: string) =>
    request<LoginResponse>("POST", "/api/auth/login", { username, password }, { skipAuthRedirect: true }),
  logout: () => request<{ status: string }>("POST", "/api/auth/logout", {}, { skipAuthRedirect: true }),
  me: () => get<User>("/api/auth/me"),
  catalog: () => get<Catalog>("/api/catalog"),
  dashboard: () => get<Dashboard>("/api/dashboard"),

  patients: (q?: string) => get<Patient[]>(`/api/patients${qs({ q })}`),
  createPatient: (body: { given_name: string; family_name: string; sex: string; birth_year: number | null }) =>
    post<Patient>("/api/patients", body),
  patientContext: (patientId: string, encounterId: string) =>
    get<PatientContext>(`/api/patients/${enc(patientId)}/context${qs({ encounter_id: encounterId })}`),

  encounters: (status: "open" | "closed" = "open") => get<EncounterListItem[]>(`/api/encounters${qs({ status })}`),
  createEncounter: (body: {
    patient_id: string;
    complaint_code: string;
    chief_complaint: string;
    complaint_source: string;
    record_source: string;
  }) => post<Encounter>("/api/encounters", body),
  encounter: (id: string) => get<EncounterDetail>(`/api/encounters/${enc(id)}`),
  addObservation: (
    encounterId: string,
    body: { code: string; value: number | string; source_type: string; verification_status: string; source_ref?: string | null },
  ) => post<Observation>(`/api/encounters/${enc(encounterId)}/observations`, body),
  addSymptom: (encounterId: string, body: { code: string; present: boolean; source_type: string }) =>
    post<{ id: string; code: string; present: boolean }>(`/api/encounters/${enc(encounterId)}/symptoms`, body),
  verifyObservation: (id: string) => post<Observation>(`/api/observations/${enc(id)}/verify`),
  setObservationStatus: (id: string, status: "superseded" | "entered_in_error", reason: string) =>
    post<Observation>(`/api/observations/${enc(id)}/status`, { status, reason }),

  protocols: () => get<Protocol[]>("/api/protocols"),
  startWorkflow: (encounterId: string, protocolId?: string, protocolVersion?: string) =>
    post<{ thread_id: string; status: string }>("/api/workflows", {
      encounter_id: encounterId,
      ...(protocolId ? { protocol_id: protocolId } : {}),
      ...(protocolVersion ? { protocol_version: protocolVersion } : {}),
    }),
  workflow: (threadId: string) => get<WorkflowDetail>(`/api/workflows/${enc(threadId)}`),

  reviews: (status?: string) => get<ReviewListItem[]>(`/api/reviews${qs({ status })}`),
  review: (id: string) => get<ReviewDetail>(`/api/reviews/${enc(id)}`),
  decide: (id: string, body: { decision: string; rationale: string; override_priority?: string | null }) =>
    post<DecisionResponse>(`/api/reviews/${enc(id)}/decision`, body),
  execute: (id: string) => post<ExecuteResponse>(`/api/reviews/${enc(id)}/execute`),

  queue: () => get<QueueResponse>("/api/queue"),
  audit: (params: { limit?: number; event_type?: string; encounter_id?: string; review_id?: string; workflow_thread_id?: string }) =>
    get<AuditEvent[]>(`/api/audit${qs(params)}`),
  auditVerify: () => get<AuditVerify>("/api/audit/verify"),
};
