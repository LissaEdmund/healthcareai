// Shared presentational pieces for conflicts, missing information, evidence and AI summaries.
import type { Conflict, Evidence, MissingItem, Summary } from "../api";
import { fmtTime, fmtValue, humanize } from "../format";
import { Badge, ProvenanceBadge } from "./Badge";

export function ConflictList({ conflicts, title = "Conflicting values" }: { conflicts: Conflict[] | undefined; title?: string }) {
  if (!conflicts || conflicts.length === 0) return null;
  return (
    <section className="conflict-box" aria-label={title}>
      <h3>
        <span aria-hidden="true">⚠ </span>
        {title} ({conflicts.length})
      </h3>
      <p className="muted">Conflicting evidence must be verified by authorized staff. No value has been chosen automatically.</p>
      <ul className="plain-list">
        {conflicts.map((c, i) => (
          <li key={`${c.field}-${i}`} className="conflict-item">
            <div>
              <strong>{humanize(c.field)}</strong> {c.scope ? <Badge tone="neutral">{humanize(c.scope)}</Badge> : null}
            </div>
            {c.message ? <div>{c.message}</div> : null}
            <ul>
              {c.values.map((v, j) => (
                <li key={j}>
                  <strong>{fmtValue(v.value)}</strong>
                  {v.unit ? ` ${v.unit}` : ""} {v.source_type ? <ProvenanceBadge sourceType={v.source_type} /> : null}{" "}
                  <span className="muted">
                    {[
                      v.source_type ? humanize(v.source_type) : null,
                      v.verification_status ? humanize(v.verification_status) : null,
                      v.source_ref ? `ref ${v.source_ref}` : null,
                      v.recorded_at ? fmtTime(v.recorded_at) : null,
                      (v.id ?? v.observation_id ?? v.symptom_id) as string | undefined,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function MissingList({ items, title = "Missing information" }: { items: MissingItem[] | undefined; title?: string }) {
  return (
    <section className="missing-box" aria-label={title}>
      <h3>{title}</h3>
      {!items || items.length === 0 ? (
        <p className="muted">None reported.</p>
      ) : (
        <ul>
          {items.map((m, i) => (
            <li key={i}>
              <strong>{m.item ?? humanize(m.field)}</strong>
              {m.detail || m.reason ? <> — {m.detail ?? m.reason}</> : null}
              {m.observation_ids?.length ? <span className="muted"> ({m.observation_ids.join(", ")})</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function EvidenceDetail({ ev }: { ev: Evidence }) {
  return (
    <dl className="evidence">
      <div>
        <dt>Value</dt>
        <dd>
          <strong>{fmtValue(ev.value)}</strong>
          {ev.unit ? ` ${ev.unit}` : ""}
        </dd>
      </div>
      {ev.observation_id ? (
        <div>
          <dt>Observation ID</dt>
          <dd className="mono">{ev.observation_id}</dd>
        </div>
      ) : null}
      {ev.symptom_id ? (
        <div>
          <dt>Symptom ID</dt>
          <dd className="mono">{ev.symptom_id}</dd>
        </div>
      ) : null}
      <div>
        <dt>Source</dt>
        <dd>
          {humanize(ev.source_type)} <ProvenanceBadge sourceType={ev.source_type} provenance={ev.provenance} />
        </dd>
      </div>
      {ev.verification_status ? (
        <div>
          <dt>Verification</dt>
          <dd>{humanize(ev.verification_status)}</dd>
        </div>
      ) : null}
      <div>
        <dt>Recorded</dt>
        <dd>
          {fmtTime(ev.recorded_at)}
          {ev.recorded_by ? <span className="muted"> by {ev.recorded_by}</span> : null}
        </dd>
      </div>
    </dl>
  );
}

export function SummaryView({ summary }: { summary: Summary | null | undefined }) {
  if (!summary) {
    return (
      <section className="card summary-card" aria-label="AI summary">
        <h3>AI summary</h3>
        <p className="muted">No summary is available for this run yet.</p>
      </section>
    );
  }
  if (summary.status === "GENERATED" && summary.text) {
    return (
      <section className="card summary-card summary-ai" aria-label="AI-generated summary">
        <h3>
          <Badge tone="ai">AI</Badge> AI-generated summary — verify against the sources
        </h3>
        <p className="summary-text">{summary.text}</p>
        <p className="muted small">
          Local model{summary.model ? `: ${summary.model}` : ""}. This summary is not a decision and does not affect the protocol evaluation.
        </p>
      </section>
    );
  }
  const unavailable = summary.status === "MODEL_UNAVAILABLE";
  return (
    <section className="card summary-card" aria-label="AI summary status">
      <h3>AI summary: {summary.status.replace(/_/g, " ")}</h3>
      <p>
        {unavailable
          ? "Local model unavailable — deterministic results above are unaffected."
          : "The AI summary was discarded — deterministic results above are unaffected."}
      </p>
      {summary.error ? <p className="muted">Detail: {summary.error}</p> : null}
      {summary.violations && summary.violations.length > 0 ? (
        <details>
          <summary>Guard findings ({summary.violations.length})</summary>
          <ul>
            {summary.violations.map((v, i) => (
              <li key={i}>{fmtValue(v)}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/** Field-level message from a 422 response. */
export function FieldError({ id, message }: { id: string; message: string | undefined }) {
  if (!message) return null;
  return (
    <span id={id} className="field-error">
      {message}
    </span>
  );
}
