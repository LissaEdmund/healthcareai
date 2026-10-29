import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Catalog, type EncounterDetail, type Observation } from "../api";
import { useAuth } from "../auth";
import { Badge, ProvenanceBadge, StatusBadge } from "../components/Badge";
import { ConflictList, FieldError } from "../components/Clinical";
import { DataState, Empty, ErrorBox, Loading } from "../components/StateViews";
import { fmtTime, humanize } from "../format";
import { useApi, useCatalog, useMutation } from "../hooks";

export function EncounterDetailPage() {
  const { id = "" } = useParams();
  const state = useApi(() => api.encounter(id), [id]);
  const catalog = useCatalog();

  return (
    <DataState state={state} label="encounter">
      {(enc) => <EncounterView enc={enc} catalog={catalog.data} reload={state.reload} />}
    </DataState>
  );
}

function EncounterView({ enc, catalog, reload }: { enc: EncounterDetail; catalog: Catalog | null; reload: () => void }) {
  const { can } = useAuth();
  const p = enc.patient;
  return (
    <>
      <div className="page-head">
        <h1>
          Encounter <span className="mono">{enc.id}</span>
        </h1>
        <button type="button" className="btn btn-small" onClick={reload}>
          Refresh
        </button>
      </div>
      <div className="card">
        <dl className="kv">
          <div>
            <dt>Synthetic patient</dt>
            <dd>
              {p.given_name} {p.family_name} <span className="mono muted">{p.id}</span> <Badge tone="synthetic">SYNTHETIC</Badge>
              <div className="muted small">
                {humanize(p.sex)}
                {p.birth_year ? `, born ${p.birth_year}` : ""}
              </div>
            </dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <StatusBadge status={enc.status} />
            </dd>
          </div>
          <div>
            <dt>Arrived</dt>
            <dd>{fmtTime(enc.arrived_at)}</dd>
          </div>
          <div>
            <dt>Chief complaint</dt>
            <dd>
              {enc.chief_complaint} <span className="muted">({humanize(enc.complaint_code)})</span>{" "}
              <ProvenanceBadge sourceType={enc.complaint_source} />
            </dd>
          </div>
          <div>
            <dt>Department / facility</dt>
            <dd>
              {enc.department} · {enc.facility_code}
            </dd>
          </div>
        </dl>
        <p>
          <Link to={`/patients/${p.id}/history?encounter=${enc.id}`}>View patient history and context →</Link>
        </p>
      </div>

      <QueueEntryCard entry={enc.synthetic_queue} />

      {enc.observations === undefined ? (
        <section className="card">
          <h2>Observations and symptoms</h2>
          <p className="muted">Not shown — your role lacks permission to read clinical observations (patient:read_history).</p>
        </section>
      ) : (
        <>
          <ConflictList conflicts={enc.conflicts} title="Conflicting observations in this encounter" />
          <ObservationsSection enc={enc} catalog={catalog} reload={reload} />
        </>
      )}

      {can("observation:record") ? <AddObservationForm encounterId={enc.id} catalog={catalog} onDone={reload} disabled={enc.status !== "open"} /> : null}

      <SymptomsSection enc={enc} catalog={catalog} reload={reload} />

      {can("triage:run") ? <TriageSection enc={enc} /> : null}
    </>
  );
}

export function QueueEntryCard({ entry }: { entry: EncounterDetail["synthetic_queue"] }) {
  return (
    <section className="card" aria-label="Synthetic queue entry">
      <h2>Synthetic queue entry</h2>
      <p className="muted small">SYNTHETIC QUEUE — not connected to any hospital system.</p>
      {!entry ? (
        <Empty>No synthetic queue entry for this encounter.</Empty>
      ) : (
        <dl className="kv">
          <div>
            <dt>Priority</dt>
            <dd>{entry.priority ? <strong className="priority">{entry.priority}</strong> : <span>Not set (no approved decision yet)</span>}</dd>
          </div>
          <div>
            <dt>Rank</dt>
            <dd>{entry.priority_rank ?? "—"}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{fmtTime(entry.updated_at)}</dd>
          </div>
          <div>
            <dt>Set by action</dt>
            <dd className="mono">{entry.updated_by_action_id ?? "—"}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function obsValue(o: Observation): string {
  return o.value_num !== null ? String(o.value_num) : (o.value_text ?? "—");
}

function ObservationsSection({ enc, catalog, reload }: { enc: EncounterDetail; catalog: Catalog | null; reload: () => void }) {
  const { can } = useAuth();
  const obs = enc.observations ?? [];
  const conflictCodes = new Set((enc.conflicts ?? []).map((c) => c.field));
  const [statusFor, setStatusFor] = useState<string | null>(null);
  const verify = useMutation();
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  async function doVerify(id: string) {
    setVerifyingId(id);
    const r = await verify.run(() => api.verifyObservation(id));
    setVerifyingId(null);
    if (r) reload();
  }

  return (
    <section className="card" aria-label="Current observations">
      <h2>Current observations ({obs.length})</h2>
      {verify.error ? <ErrorBox error={verify.error} title="Could not verify observation" /> : null}
      {obs.length === 0 ? (
        <Empty>No observations recorded for this encounter.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Observation</th>
                <th scope="col">Value</th>
                <th scope="col">Unit</th>
                <th scope="col">Source</th>
                <th scope="col">Verification</th>
                <th scope="col">Status</th>
                <th scope="col">Recorded by</th>
                <th scope="col">Recorded at</th>
                {can("observation:verify") ? <th scope="col">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {obs.map((o) => {
                const conflict = o.status === "active" && conflictCodes.has(o.code);
                return (
                  <tr key={o.id} className={conflict ? "row-conflict" : o.status !== "active" ? "row-inactive" : undefined}>
                    <td>
                      {catalog?.observation_codes[o.code]?.label ?? o.code}
                      {conflict ? (
                        <div>
                          <Badge tone="danger">⚠ Conflict</Badge>
                        </div>
                      ) : null}
                      <div className="mono muted small">{o.id}</div>
                    </td>
                    <td>
                      <strong>{obsValue(o)}</strong>
                    </td>
                    <td>{o.unit ?? "—"}</td>
                    <td>
                      {humanize(o.source_type)}
                      <div>
                        <ProvenanceBadge sourceType={o.source_type} />
                      </div>
                      {o.source_ref ? <div className="muted small">ref {o.source_ref}</div> : null}
                    </td>
                    <td>
                      <StatusBadge status={o.verification_status} />
                      {o.verified_by ? <div className="muted small">by {o.verified_by}</div> : null}
                    </td>
                    <td>
                      <StatusBadge status={o.status} />
                      {o.status_reason ? <div className="muted small">Reason: {o.status_reason}</div> : null}
                    </td>
                    <td>{o.recorded_by ?? "—"}</td>
                    <td className="nowrap">{fmtTime(o.recorded_at)}</td>
                    {can("observation:verify") ? (
                      <td>
                        {o.status === "active" ? (
                          <div className="actions">
                            {o.verification_status === "unverified" ? (
                              <button type="button" className="btn btn-small" onClick={() => void doVerify(o.id)} disabled={verifyingId === o.id}>
                                {verifyingId === o.id ? "Verifying…" : "Verify"}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="btn btn-small"
                              aria-expanded={statusFor === o.id}
                              onClick={() => setStatusFor(statusFor === o.id ? null : o.id)}
                            >
                              Supersede / Entered in error
                            </button>
                          </div>
                        ) : (
                          <span className="muted small">No actions</span>
                        )}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {statusFor ? (
        <ObservationStatusForm
          observationId={statusFor}
          onCancel={() => setStatusFor(null)}
          onDone={() => {
            setStatusFor(null);
            reload();
          }}
        />
      ) : null}
    </section>
  );
}

function ObservationStatusForm({ observationId, onCancel, onDone }: { observationId: string; onCancel: () => void; onDone: () => void }) {
  const [status, setStatus] = useState<"superseded" | "entered_in_error">("superseded");
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | undefined>();
  const m = useMutation();
  const fe = m.error?.fieldErrors ?? {};

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (reason.trim().length < 3) {
      setLocalError("A reason of at least 3 characters is required.");
      return;
    }
    setLocalError(undefined);
    const r = await m.run(() => api.setObservationStatus(observationId, status, reason.trim()));
    if (r) onDone();
  }

  return (
    <form className="subform" onSubmit={submit} noValidate aria-label={`Change status of observation ${observationId}`}>
      <h3>
        Change status of <span className="mono">{observationId}</span>
      </h3>
      <fieldset>
        <legend>New status</legend>
        <label className="radio">
          <input type="radio" name="obs-status" value="superseded" checked={status === "superseded"} onChange={() => setStatus("superseded")} />
          Superseded (replaced by a newer value)
        </label>
        <label className="radio">
          <input
            type="radio"
            name="obs-status"
            value="entered_in_error"
            checked={status === "entered_in_error"}
            onChange={() => setStatus("entered_in_error")}
          />
          Entered in error
        </label>
      </fieldset>
      <div className="field">
        <label htmlFor="obs-reason">Reason (required)</label>
        <textarea
          id="obs-reason"
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          aria-invalid={!!(localError || fe.reason)}
          aria-describedby="obs-reason-err"
        />
        <FieldError id="obs-reason-err" message={localError ?? fe.reason} />
      </div>
      {m.error && !fe.reason ? <ErrorBox error={m.error} title="Status not changed" /> : null}
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={m.busy}>
          {m.busy ? "Saving…" : "Confirm status change"}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function AddObservationForm({ encounterId, catalog, onDone, disabled }: { encounterId: string; catalog: Catalog | null; onDone: () => void; disabled: boolean }) {
  const { can } = useAuth();
  const [code, setCode] = useState("");
  const [value, setValue] = useState("");
  const [sourceType, setSourceType] = useState("clinician_measured");
  const [verified, setVerified] = useState(false);
  const [sourceRef, setSourceRef] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const m = useMutation();
  const fe = m.error?.fieldErrors ?? {};
  const meta = code && catalog ? catalog.observation_codes[code] : undefined;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(null);
    let v: number | string = value.trim();
    if (meta?.type === "number" && v !== "" && !Number.isNaN(Number(v))) v = Number(v);
    const r = await m.run(() =>
      api.addObservation(encounterId, {
        code,
        value: v,
        source_type: sourceType,
        verification_status: verified ? "verified" : "unverified",
        source_ref: sourceRef.trim() || null,
      }),
    );
    if (r) {
      setSaved(`Recorded ${r.id}.`);
      setValue("");
      setSourceRef("");
      setVerified(false);
      onDone();
    }
  }

  if (!catalog) return <Loading label="Loading observation catalog…" />;
  return (
    <form className="card" onSubmit={submit} noValidate aria-label="Add observation">
      <h2>Add observation</h2>
      {disabled ? <p className="muted">This encounter is closed; observations cannot be added.</p> : null}
      <div className="grid-form">
        <div className="field">
          <label htmlFor="o-code">Observation</label>
          <select
            id="o-code"
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setValue("");
            }}
            aria-invalid={!!fe.code}
            aria-describedby="o-code-err"
          >
            <option value="">Select…</option>
            {Object.entries(catalog.observation_codes).map(([c, mm]) => (
              <option key={c} value={c}>
                {mm.label}
                {mm.unit ? ` (${mm.unit})` : ""}
              </option>
            ))}
          </select>
          <FieldError id="o-code-err" message={fe.code} />
        </div>
        <div className="field">
          <label htmlFor="o-value">Value{meta?.unit ? ` (${meta.unit})` : ""}</label>
          {meta?.type === "text" && meta.values ? (
            <select id="o-value" value={value} onChange={(e) => setValue(e.target.value)} aria-invalid={!!fe.value} aria-describedby="o-value-err o-value-hint">
              <option value="">Select…</option>
              {meta.values.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="o-value"
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-invalid={!!fe.value}
              aria-describedby="o-value-err o-value-hint"
            />
          )}
          <span id="o-value-hint" className="muted small">
            {meta?.range ? `Data-entry range ${meta.range[0]}–${meta.range[1]} (typing-error check, not a clinical threshold)` : ""}
          </span>
          <FieldError id="o-value-err" message={fe.value} />
        </div>
        <div className="field">
          <label htmlFor="o-source">Source type</label>
          <select id="o-source" value={sourceType} onChange={(e) => setSourceType(e.target.value)} aria-invalid={!!fe.source_type} aria-describedby="o-source-err">
            {catalog.observation_sources.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
          <FieldError id="o-source-err" message={fe.source_type} />
        </div>
        <div className="field">
          <label htmlFor="o-ref">Source reference (optional)</label>
          <input id="o-ref" value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} aria-invalid={!!fe.source_ref} aria-describedby="o-ref-err" />
          <FieldError id="o-ref-err" message={fe.source_ref} />
        </div>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} disabled={!can("observation:verify")} />
        Record as verified (I have checked this value)
        {!can("observation:verify") ? <span className="muted small"> — your role cannot verify</span> : null}
      </label>
      {m.error && Object.keys(m.error.fieldErrors).length === 0 ? <ErrorBox error={m.error} title="Observation not recorded" /> : null}
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={m.busy || disabled}>
          {m.busy ? "Saving…" : "Record observation"}
        </button>
      </div>
      {saved ? (
        <p className="success" role="status">
          {saved}
        </p>
      ) : null}
    </form>
  );
}

function SymptomsSection({ enc, catalog, reload }: { enc: EncounterDetail; catalog: Catalog | null; reload: () => void }) {
  const { can } = useAuth();
  const [code, setCode] = useState("");
  const [present, setPresent] = useState<"present" | "absent" | "">("");
  const [sourceType, setSourceType] = useState("patient_reported");
  const [saved, setSaved] = useState<string | null>(null);
  const m = useMutation();
  const fe = m.error?.fieldErrors ?? {};

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(null);
    const r = await m.run(() => api.addSymptom(enc.id, { code, present: present === "present", source_type: sourceType }));
    if (r) {
      setSaved(`Recorded ${catalog?.symptom_codes[r.code] ?? r.code}: ${r.present ? "present" : "absent"}.`);
      setCode("");
      setPresent("");
      reload();
    }
  }

  const symptoms = enc.symptoms;
  return (
    <section className="card" aria-label="Symptoms">
      <h2>Symptoms</h2>
      {symptoms === undefined ? (
        <p className="muted">Recorded symptoms not shown — your role lacks permission (patient:read_history).</p>
      ) : symptoms.length === 0 ? (
        <Empty>No symptoms documented. Absence is never assumed.</Empty>
      ) : (
        <ul className="symptom-list">
          {symptoms.map((s) => (
            <li key={s.id}>
              <Badge tone={s.present ? "warn" : "neutral"}>{s.present ? "Present" : "Absent"}</Badge>{" "}
              <strong>{catalog?.symptom_codes[s.code] ?? s.code}</strong> <ProvenanceBadge sourceType={s.source_type} />{" "}
              <span className="muted small">
                {humanize(s.source_type)} · {s.recorded_by ?? "—"} · {fmtTime(s.recorded_at)} · <span className="mono">{s.id}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      {can("symptom:record") && catalog ? (
        <form className="subform" onSubmit={submit} noValidate aria-label="Record symptom">
          <h3>Record a symptom</h3>
          <div className="grid-form">
            <div className="field">
              <label htmlFor="s-code">Symptom</label>
              <select id="s-code" value={code} onChange={(e) => setCode(e.target.value)} aria-invalid={!!fe.code} aria-describedby="s-code-err">
                <option value="">Select…</option>
                {Object.entries(catalog.symptom_codes).map(([c, label]) => (
                  <option key={c} value={c}>
                    {label}
                  </option>
                ))}
              </select>
              <FieldError id="s-code-err" message={fe.code} />
            </div>
            <fieldset>
              <legend>Finding</legend>
              <label className="radio">
                <input type="radio" name="s-present" checked={present === "present"} onChange={() => setPresent("present")} /> Present
              </label>
              <label className="radio">
                <input type="radio" name="s-present" checked={present === "absent"} onChange={() => setPresent("absent")} /> Absent
              </label>
            </fieldset>
            <div className="field">
              <label htmlFor="s-source">Source</label>
              <select id="s-source" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
                <option value="patient_reported">Patient-reported</option>
                <option value="clinician_observed">Clinician-observed</option>
              </select>
              <FieldError id="s-source-err" message={fe.source_type} />
            </div>
          </div>
          {m.error && Object.keys(m.error.fieldErrors).length === 0 ? <ErrorBox error={m.error} title="Symptom not recorded" /> : null}
          <button type="submit" className="btn btn-primary" disabled={m.busy || !code || !present}>
            {m.busy ? "Saving…" : "Record symptom"}
          </button>
          {saved ? (
            <p className="success" role="status">
              {saved}
            </p>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}

function TriageSection({ enc }: { enc: EncounterDetail }) {
  const navigate = useNavigate();
  const protocols = useApi(() => api.protocols(), []);
  const [choice, setChoice] = useState("SYNTHETIC-DEMO-OPD@0.1.0");
  const m = useMutation();

  async function start() {
    const [pid, ver] = choice.split("@");
    const r = await m.run(() => api.startWorkflow(enc.id, pid, ver));
    if (r) navigate(`/workflows/${r.thread_id}`);
  }

  const valid = (protocols.data ?? []).filter((p) => p.valid && p.protocol_id && p.version);
  return (
    <section className="card" aria-label="Triage run">
      <h2>Triage workflow</h2>
      <p className="muted">
        Starting a run gathers context, evaluates the configured protocol and creates a <strong>proposal</strong> that requires nurse review.
        Nothing in the synthetic queue changes until an authorized reviewer approves it.
      </p>
      <div className="inline-form">
        <div className="field">
          <label htmlFor="t-protocol">Protocol</label>
          <select id="t-protocol" value={choice} onChange={(e) => setChoice(e.target.value)} disabled={protocols.loading}>
            {valid.length === 0 ? <option value="SYNTHETIC-DEMO-OPD@0.1.0">SYNTHETIC-DEMO-OPD 0.1.0 (default)</option> : null}
            {valid.map((p) => (
              <option key={`${p.protocol_id}@${p.version}`} value={`${p.protocol_id}@${p.version}`}>
                {p.protocol_id} {p.version} — {p.status}
                {p.evaluable ? "" : " (not evaluable)"}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => void start()} disabled={m.busy || enc.status !== "open"}>
          {m.busy ? "Starting…" : "Start triage run"}
        </button>
      </div>
      {protocols.error ? <ErrorBox error={protocols.error} title="Could not load protocols (default will be used)" /> : null}
      {m.error ? <ErrorBox error={m.error} title="Triage run not started" /> : null}

      <h3>Previous runs</h3>
      {enc.workflows.length === 0 ? (
        <Empty>No triage runs for this encounter yet.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Status</th>
                <th scope="col">Step</th>
                <th scope="col">Protocol</th>
                <th scope="col">Started</th>
                <th scope="col">Review</th>
              </tr>
            </thead>
            <tbody>
              {enc.workflows.map((w) => (
                <tr key={w.thread_id}>
                  <td className="mono">
                    <Link to={`/workflows/${w.thread_id}`}>{w.thread_id}</Link>
                  </td>
                  <td>
                    <StatusBadge status={w.status} />
                  </td>
                  <td className="mono">{w.current_step ?? "—"}</td>
                  <td className="mono">
                    {w.protocol_id} {w.protocol_version}
                  </td>
                  <td className="nowrap">{fmtTime(w.created_at)}</td>
                  <td className="mono">{w.review_id ? <Link to={`/reviews/${w.review_id}`}>{w.review_id}</Link> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
