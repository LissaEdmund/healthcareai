import { useEffect, useState, type FormEvent } from "react";
import { api, type AuditEvent } from "../api";
import { Badge, StatusBadge } from "../components/Badge";
import { DataState, ErrorBox, Loading } from "../components/StateViews";
import { fmtTime, shortHash } from "../format";
import { useApi } from "../hooks";

export function AuditPage() {
  const [eventType, setEventType] = useState("");
  const [limit, setLimit] = useState(200);
  const events = useApi(() => api.audit({ limit, event_type: eventType || undefined }), [eventType, limit]);
  const verify = useApi(() => api.auditVerify(), []);
  // Event types seen so far, so the filter offers real values (the API has no event-type listing).
  const [knownTypes, setKnownTypes] = useState<string[]>([]);
  const [custom, setCustom] = useState("");

  useEffect(() => {
    const data = events.data;
    if (!data) return;
    setKnownTypes((prev) => {
      const s = new Set(prev);
      for (const e of data) s.add(e.event_type);
      return s.size === prev.length ? prev : [...s].sort();
    });
  }, [events.data]);
  const types = eventType && !knownTypes.includes(eventType) ? [...knownTypes, eventType].sort() : knownTypes;

  function applyCustom(e: FormEvent) {
    e.preventDefault();
    setEventType(custom.trim());
  }

  return (
    <>
      <div className="page-head">
        <h1>Audit log</h1>
        <button
          type="button"
          className="btn btn-small"
          onClick={() => {
            events.reload();
            verify.reload();
          }}
        >
          Refresh
        </button>
      </div>

      <section className="card" aria-label="Chain verification">
        <h2>Hash-chain verification</h2>
        {verify.loading && !verify.data ? (
          <Loading label="Verifying chain…" />
        ) : verify.error ? (
          <ErrorBox error={verify.error} title="Could not verify chain" onRetry={verify.reload} />
        ) : verify.data ? (
          verify.data.valid ? (
            <p>
              <Badge tone="ok">✓ Chain intact</Badge> {verify.data.events_checked} events checked.
            </p>
          ) : (
            <p role="alert">
              <Badge tone="danger">✕ Chain BROKEN</Badge> at sequence {verify.data.broken_at_seq} after {verify.data.events_checked} valid events.
            </p>
          )
        ) : null}
      </section>

      <div className="filters">
        <div className="field">
          <label htmlFor="a-type">Event type</label>
          <select id="a-type" value={eventType} onChange={(e) => setEventType(e.target.value)}>
            <option value="">All event types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <form className="inline-form" onSubmit={applyCustom}>
          <div className="field">
            <label htmlFor="a-custom">Or type an event type</label>
            <input id="a-custom" className="mono" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="e.g. review_decided" />
          </div>
          <button type="submit" className="btn">
            Apply
          </button>
        </form>
        <div className="field">
          <label htmlFor="a-limit">Rows</label>
          <select id="a-limit" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[50, 200, 500, 1000].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      <DataState state={events} label="audit events" isEmpty={(d) => d.length === 0} empty="No audit events match this filter.">
        {(rows) => <AuditTable rows={rows} />}
      </DataState>
    </>
  );
}

function AuditTable({ rows }: { rows: AuditEvent[] }) {
  return (
    <div className="table-wrap">
      <table className="audit-table">
        <thead>
          <tr>
            <th scope="col">Seq</th>
            <th scope="col">Time</th>
            <th scope="col">Event type</th>
            <th scope="col">Actor</th>
            <th scope="col">Tool</th>
            <th scope="col">Encounter / review</th>
            <th scope="col">Approval state</th>
            <th scope="col">Outcome</th>
            <th scope="col">Error</th>
            <th scope="col">Input / output refs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.seq}>
              <td>{e.seq}</td>
              <td className="nowrap">{fmtTime(e.ts)}</td>
              <td className="mono">
                {e.event_type}
                {e.action ? <div className="muted small">{e.action}</div> : null}
              </td>
              <td>
                <Badge tone={e.actor_type === "agent" ? "ai" : e.actor_type === "system" ? "neutral" : "info"}>{e.actor_type}</Badge>
                <div className="mono small">{e.actor_id ?? "—"}</div>
                {e.actor_role ? <div className="muted small">{e.actor_role}</div> : null}
              </td>
              <td className="mono">{e.tool_name ?? "—"}</td>
              <td className="mono small">
                {e.encounter_id ?? "—"}
                {e.review_id ? <div>{e.review_id}</div> : null}
                {e.workflow_thread_id ? <div className="muted">{e.workflow_thread_id}</div> : null}
              </td>
              <td>{e.approval_state ?? "—"}</td>
              <td>
                <StatusBadge status={e.outcome} />
              </td>
              <td className="break small">{e.error ?? "—"}</td>
              <td className="mono small">
                <div title={e.input_ref ?? undefined}>in: {shortHash(e.input_ref)}</div>
                <div title={e.output_ref ?? undefined}>out: {shortHash(e.output_ref)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
