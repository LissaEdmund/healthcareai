import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type PatientContext } from "../api";
import { Badge, ProvenanceBadge, StatusBadge } from "../components/Badge";
import { ConflictList, MissingList } from "../components/Clinical";
import { DataState, Empty } from "../components/StateViews";
import { fmtTime, fmtValue, humanize } from "../format";
import { useApi } from "../hooks";

export function PatientHistoryPage() {
  const { pid = "" } = useParams();
  const [params] = useSearchParams();
  const encounterId = params.get("encounter") ?? "";
  const state = useApi(encounterId ? () => api.patientContext(pid, encounterId) : null, [pid, encounterId]);

  if (!encounterId) {
    return (
      <div className="error-box" role="alert">
        <strong>No encounter selected.</strong> Patient context is always retrieved for a specific encounter. Open it from an{" "}
        <Link to="/encounters">encounter</Link>.
      </div>
    );
  }
  return (
    <>
      <div className="page-head">
        <h1>Patient history and context</h1>
        <button type="button" className="btn btn-small" onClick={state.reload}>
          Refresh
        </button>
      </div>
      <p>
        <Link to={`/encounters/${encounterId}`}>← Back to encounter {encounterId}</Link>
      </p>
      <DataState state={state} label="patient context">
        {(ctx) => <ContextView ctx={ctx} />}
      </DataState>
    </>
  );
}

function ContextView({ ctx }: { ctx: PatientContext }) {
  return (
    <>
      <p className="data-label" role="note">
        {ctx.data_label}
      </p>

      {ctx.categories_withheld.length > 0 ? (
        <section className="withheld-box" aria-label="Withheld categories">
          <h2>Categories withheld</h2>
          <ul>
            {ctx.categories_withheld.map((c) => (
              <li key={c}>
                <strong>{humanize(c)}</strong>: not shown — your role lacks permission
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {ctx.patient ? (
        <section className="card" aria-label="Demographics">
          <h2>
            {ctx.patient.display_name} <Badge tone="synthetic">SYNTHETIC</Badge>
          </h2>
          <p>
            <span className="mono">{ctx.patient.id}</span> · {humanize(ctx.patient.sex)}
            {ctx.patient.birth_year ? ` · born ${ctx.patient.birth_year}` : ""}
          </p>
        </section>
      ) : null}

      {ctx.recurring_complaint ? (
        <section className={`card ${ctx.recurring_complaint.detected ? "recurring-box" : ""}`} aria-label="Recurring complaint">
          <h2>Recurring complaint</h2>
          {ctx.recurring_complaint.detected ? (
            <>
              <p>
                <Badge tone="warn">Recurring</Badge> Complaint “{humanize(ctx.recurring_complaint.complaint_code)}” was also documented in{" "}
                {ctx.recurring_complaint.prior_encounter_ids.length} previous encounter(s) within {ctx.recurring_complaint.lookback_days} days:{" "}
                <span className="mono">{ctx.recurring_complaint.prior_encounter_ids.join(", ")}</span>
              </p>
              {ctx.recurring_complaint.statement ? <p className="statement">{ctx.recurring_complaint.statement}</p> : null}
            </>
          ) : (
            <p>
              No recurrence of “{humanize(ctx.recurring_complaint.complaint_code)}” found in the searched records within{" "}
              {ctx.recurring_complaint.lookback_days} days.
            </p>
          )}
        </section>
      ) : null}

      <MissingList items={ctx.missing_information} />
      <ConflictList conflicts={ctx.conflicts} title="Conflicts" />

      {ctx.record_sources ? (
        <section className="card" aria-label="Record sources">
          <h2>Record sources searched</h2>
          {ctx.record_sources.length === 0 ? (
            <Empty>No record sources registered for this patient.</Empty>
          ) : (
            <ul>
              {ctx.record_sources.map((s) => (
                <li key={s.source_type}>
                  <strong>{humanize(s.source_type)}</strong>: <Badge tone={s.status === "available" ? "ok" : "warn"}>{humanize(s.status)}</Badge>
                  {s.note ? <span className="muted"> — {s.note}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {ctx.previous_encounters ? (
        <section aria-label="Previous encounters">
          <h2>Previous encounters ({ctx.previous_encounters.length})</h2>
          <p className="muted small">Historical records are context only and are never used as evidence for protocol criteria.</p>
          {ctx.previous_encounters.length === 0 ? (
            <Empty>No previous encounters found in the searched records. This does not mean none occurred.</Empty>
          ) : (
            ctx.previous_encounters.map((p) => (
              <article key={p.id} className="card history-encounter">
                <h3>
                  {fmtTime(p.arrived_at)} — {p.chief_complaint} <span className="muted">({humanize(p.complaint_code)})</span>
                </h3>
                <p className="muted small">
                  <span className="mono">{p.id}</span> · record source: {humanize(p.record_source)}
                </p>
                {p.notes.length === 0 ? (
                  <p className="muted">No documented notes for this encounter.</p>
                ) : (
                  <ul className="plain-list notes-list">
                    {p.notes.map((n) => (
                      <li key={n.id} className="note">
                        <div className="note-head">
                          <Badge tone="neutral">{humanize(n.category)}</Badge> <ProvenanceBadge provenance={n.provenance} />
                        </div>
                        <blockquote>{n.content}</blockquote>
                        <div className="muted small">
                          Source: {humanize(n.source_type)}
                          {n.source_ref ? (
                            <>
                              {" "}
                              · ref <span className="mono">{n.source_ref}</span>
                            </>
                          ) : null}{" "}
                          · recorded {fmtTime(n.recorded_at)}
                          {n.recorded_by ? ` by ${n.recorded_by}` : ""}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                {p.observations.length > 0 ? (
                  <details>
                    <summary>Observations recorded at that encounter ({p.observations.length})</summary>
                    <ul>
                      {p.observations.map((o) => (
                        <li key={o.id}>
                          {o.label}: <strong>{fmtValue(o.value)}</strong> {o.unit ?? ""} <ProvenanceBadge provenance={o.provenance} />{" "}
                          <StatusBadge status={o.verification_status} /> <span className="muted small">{fmtTime(o.recorded_at)}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </article>
            ))
          )}
        </section>
      ) : null}
      <p className="muted small">Context generated {fmtTime(ctx.generated_at)}.</p>
    </>
  );
}
