import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type WorkflowDetail } from "../api";
import { useAuth } from "../auth";
import { Badge, StatusBadge } from "../components/Badge";
import { SummaryView } from "../components/Clinical";
import { EvaluationView, UrgentAlert } from "../components/EvaluationView";
import { DataState, Empty } from "../components/StateViews";
import { fmtTime } from "../format";
import { useApi } from "../hooks";

const POLL_MS = 1500;
const FAILURE_STATUSES = new Set([
  "VALIDATION_FAILED",
  "CONTEXT_UNAVAILABLE",
  "EVALUATION_FAILED",
  "REVIEW_CREATION_FAILED",
  "ACTION_FAILED",
  "ERROR",
]);
const ENDED_STATUSES = new Set([...FAILURE_STATUSES, "COMPLETED", "REJECTED_NO_ACTION", "CLARIFICATION_REQUESTED"]);

const PIPELINE = [
  "validate_request",
  "retrieve_context",
  "retrieve_protocol",
  "evaluate",
  "summarize",
  "create_review",
  "await_decision",
  "execute_action",
  "verify",
  "finalize",
];

export function WorkflowPage() {
  const { threadId = "" } = useParams();
  const state = useApi(() => api.workflow(threadId), [threadId]);
  const running = state.data?.run.status === "RUNNING";

  useEffect(() => {
    if (!running || state.loading || state.error) return;
    const t = window.setTimeout(state.reload, POLL_MS);
    return () => window.clearTimeout(t);
  }, [running, state.loading, state.error, state.data, state.reload]);

  return (
    <>
      <div className="page-head">
        <h1>
          Triage run <span className="mono">{threadId}</span>
        </h1>
        <button type="button" className="btn btn-small" onClick={state.reload} disabled={state.loading}>
          {state.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <DataState state={state} label="triage run">
        {(d) => <WorkflowView d={d} />}
      </DataState>
    </>
  );
}

function WorkflowView({ d }: { d: WorkflowDetail }) {
  const { can } = useAuth();
  const { run, state } = d;
  const ev = state.evaluation;
  const reviewId = state.review_id ?? run.review_id;
  const paused = d.paused_for_review || run.status === "AWAITING_REVIEW";
  const steps = state.steps ?? [];
  const failed = FAILURE_STATUSES.has(run.status);

  return (
    <>
      {ev?.urgent_flag ? <UrgentAlert message={ev.urgent_message} /> : null}

      <div className="card">
        <dl className="kv">
          <div>
            <dt>Run status</dt>
            <dd>
              <StatusBadge status={run.status} />
              {run.status === "RUNNING" ? (
                <span className="muted small" role="status">
                  {" "}
                  <span className="spinner" aria-hidden="true" /> In progress — current step: <span className="mono">{run.current_step ?? "queued"}</span>{" "}
                  (refreshing every 1.5 s)
                </span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt>Encounter</dt>
            <dd className="mono">
              <Link to={`/encounters/${run.encounter_id}`}>{run.encounter_id}</Link>
            </dd>
          </div>
          <div>
            <dt>Protocol requested</dt>
            <dd className="mono">
              {run.protocol_id} {run.protocol_version}
            </dd>
          </div>
          <div>
            <dt>Started by</dt>
            <dd>
              {run.started_by} at {fmtTime(run.created_at)}
            </dd>
          </div>
          <div>
            <dt>Last update</dt>
            <dd>{fmtTime(run.updated_at)}</dd>
          </div>
          {reviewId ? (
            <div>
              <dt>Nurse review</dt>
              <dd className="mono">{can("review:read") ? <Link to={`/reviews/${reviewId}`}>{reviewId}</Link> : reviewId}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      {paused ? (
        <div className="paused-box" role="status">
          <strong>Awaiting nurse review — the synthetic queue has NOT been changed.</strong>
          {reviewId ? (
            <p>
              <Link to={`/reviews/${reviewId}`} className="btn btn-primary">
                Open review {reviewId}
              </Link>
            </p>
          ) : null}
        </div>
      ) : null}

      {failed || (ENDED_STATUSES.has(run.status) && d.recovery) ? (
        <div className={failed ? "error-box" : "info-box"} role={failed ? "alert" : "status"}>
          <strong>{failed ? "Run ended without completing" : "Run ended"}: {run.status.replace(/_/g, " ")}</strong>
          {d.recovery ? <p>What to do: {d.recovery}</p> : null}
          {run.last_error ? <p className="muted">Error: {run.last_error}</p> : null}
        </div>
      ) : null}

      {state.errors && state.errors.length > 0 ? (
        <section className="card" aria-label="Run errors">
          <h2>Errors reported by the run</h2>
          <ul>
            {state.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card" aria-label="Step timeline">
        <h2>Step timeline (tool calls)</h2>
        <p className="muted small">Each step lists the tool and the MCP server or component that executed it.</p>
        {steps.length === 0 && run.status !== "RUNNING" ? (
          <Empty>No steps were recorded for this run.</Empty>
        ) : (
          <ol className="timeline">
            {steps.map((s, i) => (
              <li key={`${s.step}-${i}`} className={`timeline-item step-${s.status}`}>
                <div className="timeline-head">
                  <span className="mono step-name">{s.step}</span> <StatusBadge status={s.status} />
                </div>
                <dl className="kv kv-compact">
                  <div>
                    <dt>Tool</dt>
                    <dd className="mono">{s.tool ?? "— (internal step)"}</dd>
                  </div>
                  <div>
                    <dt>Server</dt>
                    <dd>{s.server ? <Badge tone={s.server === "local model" ? "ai" : "info"}>{s.server}</Badge> : <span className="muted">workflow engine</span>}</dd>
                  </div>
                  <div>
                    <dt>Detail</dt>
                    <dd className="break">{s.detail || "—"}</dd>
                  </div>
                  <div>
                    <dt>Time</dt>
                    <dd className="small">
                      {fmtTime(s.started_at)} → {fmtTime(s.finished_at)}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
            {run.status === "RUNNING" && (steps.length === 0 || steps[steps.length - 1].step !== run.current_step) ? (
              <li className="timeline-item step-running">
                <div className="timeline-head">
                  <span className="mono step-name">{run.current_step ?? "queued"}</span> <StatusBadge status="RUNNING" />
                </div>
                <p className="muted small">In progress…</p>
              </li>
            ) : null}
          </ol>
        )}
        <details>
          <summary>Workflow outline</summary>
          <p className="mono small">{PIPELINE.join(" → ")}</p>
        </details>
      </section>

      {state.protocol_document ? (
        <section className="card" aria-label="Protocol document">
          <h2>Protocol document read via filesystem (borrowed) MCP server</h2>
          <p>
            <span className="mono">{state.protocol_document.path}</span>{" "}
            {state.protocol_document.ok ? <Badge tone="ok">✓ read</Badge> : <Badge tone="danger">✕ not read</Badge>}
          </p>
          {state.protocol_document.sha256 ? <p className="mono small break">sha256 {state.protocol_document.sha256}</p> : null}
          {state.protocol_document.error ? <p className="muted">{state.protocol_document.error}</p> : null}
        </section>
      ) : null}

      {ev ? <EvaluationView evaluation={ev} /> : run.status === "RUNNING" ? null : <Empty>No evaluation was produced for this run.</Empty>}

      {state.summary || ev ? <SummaryView summary={state.summary} /> : null}

      {state.review ? (
        <section className="card" aria-label="Review outcome">
          <h2>Nurse review</h2>
          <p>
            <StatusBadge status={state.review.status} />{" "}
            {state.review.decided_by ? (
              <>
                Decision by <strong>{state.review.decided_by}</strong> ({state.review.decision?.replace(/_/g, " ")}) at{" "}
                {fmtTime(state.review.decided_at)}
              </>
            ) : (
              "Requires nurse review — no decision recorded yet."
            )}
          </p>
        </section>
      ) : null}
    </>
  );
}
