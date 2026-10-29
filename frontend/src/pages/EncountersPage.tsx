import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Patient } from "../api";
import { useAuth } from "../auth";
import { Badge, StatusBadge } from "../components/Badge";
import { FieldError } from "../components/Clinical";
import { DataState, ErrorBox } from "../components/StateViews";
import { fmtTime, humanize } from "../format";
import { useApi, useCatalog, useMutation } from "../hooks";

export function EncountersPage() {
  const { can } = useAuth();
  const list = useApi(() => api.encounters("open"), []);
  const [patient, setPatient] = useState<Patient | null>(null);

  return (
    <>
      <div className="page-head">
        <h1>Open encounters</h1>
        <button type="button" className="btn btn-small" onClick={list.reload} disabled={list.loading}>
          {list.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <DataState state={list} label="encounters" isEmpty={(d) => d.length === 0} empty="No open encounters. Register one below.">
        {(rows) => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Encounter</th>
                  <th scope="col">Synthetic patient</th>
                  <th scope="col">Arrived</th>
                  <th scope="col">Chief complaint</th>
                  <th scope="col">Synthetic queue priority</th>
                  <th scope="col">Latest review</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">
                      <Link to={`/encounters/${e.id}`}>{e.id}</Link>
                    </td>
                    <td>
                      {e.given_name} {e.family_name}
                      <div className="mono muted small">{e.patient_id}</div>
                    </td>
                    <td className="nowrap">{fmtTime(e.arrived_at)}</td>
                    <td>
                      {e.chief_complaint}
                      <div className="muted small">{humanize(e.complaint_code)}</div>
                    </td>
                    <td>{e.synthetic_queue_priority ?? <span className="muted">Not set</span>}</td>
                    <td>{e.latest_review_status ? <StatusBadge status={e.latest_review_status} /> : <span className="muted">None</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>

      {can("encounter:create") || can("patient:create") ? (
        <section className="intake" aria-label="Intake">
          <h2>Intake (synthetic patients only)</h2>
          <div className="grid-2">
            {can("patient:create") ? <NewPatientForm onCreated={setPatient} /> : null}
            {can("encounter:create") ? <NewEncounterForm patient={patient} onPatient={setPatient} /> : null}
          </div>
        </section>
      ) : null}
    </>
  );
}

function NewPatientForm({ onCreated }: { onCreated: (p: Patient) => void }) {
  const [given, setGiven] = useState("");
  const [family, setFamily] = useState("");
  const [sex, setSex] = useState("unknown");
  const [birthYear, setBirthYear] = useState("");
  const [created, setCreated] = useState<Patient | null>(null);
  const m = useMutation();
  const fe = m.error?.fieldErrors ?? {};

  async function submit(e: FormEvent) {
    e.preventDefault();
    setCreated(null);
    let year: number | null = null;
    if (birthYear.trim()) {
      year = Number(birthYear);
      if (!Number.isInteger(year)) {
        // let the backend respond with its own validation message
        year = birthYear as unknown as number;
      }
    }
    const p = await m.run(() => api.createPatient({ given_name: given.trim(), family_name: family.trim(), sex, birth_year: year }));
    if (p) {
      setCreated(p);
      onCreated(p);
      setGiven("");
      setFamily("");
      setBirthYear("");
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate aria-label="Register synthetic patient">
      <h3>1. Register a synthetic patient</h3>
      <p className="muted small">Use invented names only. Never enter real patient details.</p>
      <div className="field">
        <label htmlFor="p-given">Given name (synthetic)</label>
        <input id="p-given" value={given} onChange={(e) => setGiven(e.target.value)} aria-invalid={!!fe.given_name} aria-describedby="p-given-err" />
        <FieldError id="p-given-err" message={fe.given_name} />
      </div>
      <div className="field">
        <label htmlFor="p-family">Family name (synthetic)</label>
        <input id="p-family" value={family} onChange={(e) => setFamily(e.target.value)} aria-invalid={!!fe.family_name} aria-describedby="p-family-err" />
        <FieldError id="p-family-err" message={fe.family_name} />
      </div>
      <div className="field">
        <label htmlFor="p-sex">Sex</label>
        <select id="p-sex" value={sex} onChange={(e) => setSex(e.target.value)} aria-invalid={!!fe.sex} aria-describedby="p-sex-err">
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="unknown">Unknown</option>
        </select>
        <FieldError id="p-sex-err" message={fe.sex} />
      </div>
      <div className="field">
        <label htmlFor="p-year">Birth year (optional)</label>
        <input
          id="p-year"
          inputMode="numeric"
          value={birthYear}
          onChange={(e) => setBirthYear(e.target.value)}
          aria-invalid={!!fe.birth_year}
          aria-describedby="p-year-err"
        />
        <FieldError id="p-year-err" message={fe.birth_year} />
      </div>
      {m.error && Object.keys(fe).length === 0 ? <ErrorBox error={m.error} title="Patient not created" /> : null}
      {m.error && Object.keys(fe).length > 0 ? (
        <p className="field-error" role="alert">
          Please correct the highlighted fields.
        </p>
      ) : null}
      <button type="submit" className="btn btn-primary" disabled={m.busy}>
        {m.busy ? "Creating…" : "Create synthetic patient"}
      </button>
      {created ? (
        <p className="success" role="status">
          Created <span className="mono">{created.id}</span> ({created.given_name} {created.family_name}). Selected for the encounter form.
        </p>
      ) : null}
    </form>
  );
}

function NewEncounterForm({ patient, onPatient }: { patient: Patient | null; onPatient: (p: Patient | null) => void }) {
  const navigate = useNavigate();
  const catalog = useCatalog();
  const [query, setQuery] = useState("");
  const [patientId, setPatientId] = useState("");
  const [complaintCode, setComplaintCode] = useState("");
  const [chief, setChief] = useState("");
  const [complaintSource, setComplaintSource] = useState("patient_reported");
  const [recordSource, setRecordSource] = useState("electronic_record");
  const search = useMutation();
  const [results, setResults] = useState<Patient[] | null>(null);
  const m = useMutation();
  const fe = m.error?.fieldErrors ?? {};

  const effectivePatientId = patientId || patient?.id || "";

  async function doSearch(e: FormEvent) {
    e.preventDefault();
    const r = await search.run(() => api.patients(query.trim() || undefined));
    if (r) setResults(r);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const enc = await m.run(() =>
      api.createEncounter({
        patient_id: effectivePatientId,
        complaint_code: complaintCode,
        chief_complaint: chief.trim(),
        complaint_source: complaintSource,
        record_source: recordSource,
      }),
    );
    if (enc) navigate(`/encounters/${enc.id}`);
  }

  return (
    <div className="card">
      <h3>2. Open an encounter</h3>
      <form onSubmit={doSearch} className="inline-form" aria-label="Find synthetic patient">
        <div className="field">
          <label htmlFor="pt-search">Find existing synthetic patient</label>
          <input id="pt-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="ID or name" />
        </div>
        <button type="submit" className="btn" disabled={search.busy}>
          {search.busy ? "Searching…" : "Search"}
        </button>
      </form>
      {search.error ? <ErrorBox error={search.error} title="Search failed" /> : null}
      {results ? (
        results.length === 0 ? (
          <p className="muted">No matching synthetic patients.</p>
        ) : (
          <ul className="pick-list" aria-label="Search results">
            {results.slice(0, 10).map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={`btn btn-small ${effectivePatientId === p.id ? "btn-primary" : ""}`}
                  aria-pressed={effectivePatientId === p.id}
                  onClick={() => {
                    setPatientId(p.id);
                    onPatient(p);
                  }}
                >
                  {p.given_name} {p.family_name} <span className="mono">{p.id}</span>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}

      <form onSubmit={submit} noValidate aria-label="Create encounter">
        <div className="field">
          <label htmlFor="e-patient">Synthetic patient ID</label>
          <input
            id="e-patient"
            className="mono"
            value={effectivePatientId}
            onChange={(e) => {
              setPatientId(e.target.value);
              if (patient && e.target.value !== patient.id) onPatient(null);
            }}
            placeholder="SYN-P-…"
            aria-invalid={!!fe.patient_id}
            aria-describedby="e-patient-err"
          />
          <FieldError id="e-patient-err" message={fe.patient_id} />
        </div>
        <div className="field">
          <label htmlFor="e-code">Complaint code</label>
          {catalog.error ? <ErrorBox error={catalog.error} title="Could not load catalog" onRetry={catalog.reload} /> : null}
          <select
            id="e-code"
            value={complaintCode}
            onChange={(e) => setComplaintCode(e.target.value)}
            disabled={!catalog.data}
            aria-invalid={!!fe.complaint_code}
            aria-describedby="e-code-err"
          >
            <option value="">{catalog.loading ? "Loading…" : "Select…"}</option>
            {catalog.data
              ? Object.entries(catalog.data.complaint_codes).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))
              : null}
          </select>
          <FieldError id="e-code-err" message={fe.complaint_code} />
        </div>
        <div className="field">
          <label htmlFor="e-chief">Chief complaint (free text)</label>
          <textarea id="e-chief" rows={2} value={chief} onChange={(e) => setChief(e.target.value)} aria-invalid={!!fe.chief_complaint} aria-describedby="e-chief-err" />
          <FieldError id="e-chief-err" message={fe.chief_complaint} />
        </div>
        <div className="field">
          <label htmlFor="e-csrc">Complaint source</label>
          <select id="e-csrc" value={complaintSource} onChange={(e) => setComplaintSource(e.target.value)}>
            <option value="patient_reported">Patient-reported</option>
            <option value="electronic_record">Electronic record (synthetic)</option>
            <option value="paper_record_transcribed">Paper record, transcribed (synthetic)</option>
          </select>
          <FieldError id="e-csrc-err" message={fe.complaint_source} />
        </div>
        <div className="field">
          <label htmlFor="e-rsrc">Record source</label>
          <select id="e-rsrc" value={recordSource} onChange={(e) => setRecordSource(e.target.value)}>
            <option value="electronic_record">Electronic record (synthetic)</option>
            <option value="paper_record_transcribed">Paper record, transcribed (synthetic)</option>
          </select>
          <FieldError id="e-rsrc-err" message={fe.record_source} />
        </div>
        {m.error && Object.keys(fe).length === 0 ? <ErrorBox error={m.error} title="Encounter not created" /> : null}
        {m.error && Object.keys(fe).length > 0 ? (
          <p className="field-error" role="alert">
            Please correct the highlighted fields.
          </p>
        ) : null}
        <button type="submit" className="btn btn-primary" disabled={m.busy}>
          {m.busy ? "Creating…" : "Create encounter"}
        </button>
        <p className="muted small">
          A <Badge tone="synthetic">synthetic queue</Badge> entry is created with no priority. Only an approved nurse decision can set it.
        </p>
      </form>
    </div>
  );
}
