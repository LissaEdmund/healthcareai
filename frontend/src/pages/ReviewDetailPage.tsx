import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ExecuteResponse, type ReviewDetail } from "../api";
import { useAuth } from "../auth";
import { Badge, StatusBadge, UrgentBadge } from "../components/Badge";
import { FieldError, SummaryView } from "../components/Clinical";
import { EvaluationView, UrgentAlert } from "../components/EvaluationView";
import { DataState, ErrorBox } from "../components/StateViews";
import { fmtTime, humanize } from "../format";
import { useApi, useMutation } from "../hooks";
import { QueueEntryCard } from "./EncounterDetailPage";

const POLL_MS = 1500;
const MAX_POLLS = 40;

export function ReviewDetailPage() {
  const { id = "" } = useParams();
  const state = useApi(() => api.review(id), [id]);
  const [queueEffect, setQueueEffect] = useState<string | null>(null);
  const polls = useRef(0);
  const approvedWaiting = state.data?.status === "APPROVED" && !!state.data.workflow_thread_id;

  // After approval the workflow applies and verifies the action in the background; follow it briefly.
  useEffect(() => {
    if (!approvedWaiting || state.loading || state.error || polls.current >= MAX_POLLS) return;
    const t = window.setTimeout(() => {
      polls.current += 1;
      state.reload();
    }, POLL_MS);
    return () => window.clearTimeout(t);
  }, [approvedWaiting, state.loading, state.error, state.data, state.reload]);

  return (
    <>
      <div className="page-head">
        <h1>
          Nurse review <span className="mono">{id}</span>
        </h1>
        <button type="button" className="btn btn-small" onClick={state.reload} disabled={state.loading}>
          {state.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <p>
        <Link to="/reviews">← Review queue</Link>
      </p>
      <DataState state={state} label="review">
        {(r) => (
          <ReviewView
            r={r}
            queueEffect={queueEffect}
            following={approvedWaiting && polls.current < MAX_POLLS}
            onDecided={(effect) => {
              setQueueEffect(effect);
              polls.current = 0;
              state.reload();
            }}
            reload={state.reload}
          />
        )}
      </DataState>
    </>
  );
}

function ReviewView({
  r,
  queueEffect,
  following,
  onDecided,
  reload,
}: {
  r: ReviewDetail;
  queueEffect: string | null;
  following: boolean;
  onDecided: (effect: string) => void;
  reload: () => void;
}) {
  const { can } = useAuth();
  const ev = r.evaluation.result;
  return (
    <>
      {ev.urgent_flag ? <UrgentAlert message={ev.urgent_message} /> : null}

      <div className="card">
        <div className="review-item-head">
          {r.evaluation.urgent_flag ? <UrgentBadge /> : null} <StatusBadge status={r.status} />
        </div>
        <dl className="kv">
          <div>
            <dt>Synthetic patient</dt>
            <dd>
              {r.patient.given_name} {r.patient.family_name} <span className="mono muted">{r.patient.id}</span>{" "}
              <Badge tone="synthetic">SYNTHETIC</Badge>
            </dd>
          </div>
          <div>
            <dt>Encounter</dt>
            <dd>
              <Link to={`/encounters/${r.encounter.id}`} className="mono">
                {r.encounter.id}
              </Link>{" "}
              — {r.encounter.chief_complaint} <span className="muted">({humanize(r.encounter.complaint_code)})</span>
              <div>
                <Link to={`/patients/${r.patient.id}/history?encounter=${r.encounter.id}`}>Patient history and context →</Link>
              </div>
            </dd>
          </div>
          <div>
            <dt>Requested</dt>
            <dd>
              {fmtTime(r.requested_at)} by {r.requested_by} (workflow on behalf of this user)
            </dd>
          </div>
          {r.workflow_thread_id ? (
            <div>
              <dt>Triage run</dt>
              <dd className="mono">{can("triage:run") ? <Link to={`/workflows/${r.workflow_thread_id}`}>{r.workflow_thread_id}</Link> : r.workflow_thread_id}</dd>
            </div>
          ) : null}
          <div>
            <dt>Action on approval</dt>
            <dd>
              {humanize(r.action_type)} <span className="muted small">(synthetic queue only)</span>
            </dd>
          </div>
          <div>
            <dt>Proposed priority</dt>
            <dd>{r.proposed_priority ? <strong className="priority">{r.proposed_priority}</strong> : <em>No priority proposed</em>}</dd>
          </div>
        </dl>
      </div>

      {queueEffect ? (
        <div className="info-box" role="status">
          <strong>Decision recorded.</strong> {queueEffect}
        </div>
      ) : null}

      <DecisionPanel r={r} onDecided={onDecided} />

      {following ? (
        <p className="muted" role="status">
          <span className="spinner" aria-hidden="true" /> Waiting for the workflow to apply and verify the approved action…
        </p>
      ) : null}

      <ActionPanel r={r} reload={reload} following={following} />

      <QueueEntryCard entry={r.queue_entry} />

      <EvaluationView evaluation={ev} />
      <SummaryView summary={r.summary} />
    </>
  );
}

function DecisionPanel({ r, onDecided }: { r: ReviewDetail; onDecided: (effect: string) => void }) {
  const { user, can } = useAuth();
  const canApprove = r.evaluation.status === "PROPOSED";
  const [decision, setDecision] = useState<string>("");
  const [rationale, setRationale] = useState("");
  const [override, setOverride] = useState("");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});
  const m = useMutation();
  const fe = { ...(m.error?.fieldErrors ?? {}), ...localErrors };

  if (r.status !== "PENDING") {
    return (
      <section className="card" aria-label="Decision">
        <h2>Decision</h2>
        {r.decided_by ? (
          <>
            <p>
              <StatusBadge status={r.status} /> Decision by <strong>{r.decided_by}</strong>: {humanize(r.decision)} at {fmtTime(r.decided_at)}
            </p>
            {r.approved_priority ? (
              <p>
                Approved priority: <strong className="priority">{r.approved_priority}</strong>
                {r.decision === "override" ? <Badge tone="warn">Override of proposal</Badge> : null}
              </p>
            ) : null}
            {r.rationale ? (
              <blockquote>
                <strong>Rationale:</strong> {r.rationale}
              </blockquote>
            ) : null}
          </>
        ) : (
          <p className="muted">No decision recorded.</p>
        )}
      </section>
    );
  }

  if (!can("review:decide")) {
    return (
      <section className="card" aria-label="Decision">
        <h2>Decision</h2>
        <p>Requires nurse review. Your role cannot record decisions.</p>
      </section>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!decision) errs.decision = "Choose a decision.";
    if (rationale.trim().length < 3) errs.rationale = "A rationale of at least 3 characters is required.";
    if (decision === "override" && !override) errs.override_priority = "Choose the priority level to apply.";
    setLocalErrors(errs);
    if (Object.keys(errs).length) return;
    const res = await m.run(() =>
      api.decide(r.id, { decision, rationale: rationale.trim(), override_priority: decision === "override" ? override : null }),
    );
    if (res) onDecided(res.queue_effect);
  }

  const options: { value: string; label: string; disabled?: boolean; hint?: string }[] = [
    {
      value: "approve",
      label: `Approve proposal${r.proposed_priority ? ` (${r.proposed_priority})` : ""}`,
      disabled: !canApprove,
      hint: canApprove ? "Applies the proposed priority to the synthetic queue." : "Unavailable: the evaluation did not propose a priority.",
    },
    { value: "override", label: "Override — choose a different level", hint: "Applies the level you choose to the synthetic queue." },
    { value: "request_clarification", label: "Request clarification", hint: "No queue change. Record or verify information, then start a new run." },
    { value: "reject", label: "Reject proposal", hint: "No queue change." },
  ];

  return (
    <form className="card decision-form" onSubmit={submit} noValidate aria-label="Record decision">
      <h2>Your decision</h2>
      <p className="signing">
        Signing as <strong>{user?.display_name}</strong> <span className="muted">({user?.role})</span>
      </p>
      <fieldset aria-describedby="d-decision-err">
        <legend>Decision</legend>
        {options.map((o) => (
          <label key={o.value} className={`radio ${o.disabled ? "disabled" : ""}`}>
            <input type="radio" name="decision" value={o.value} checked={decision === o.value} disabled={o.disabled} onChange={() => setDecision(o.value)} />
            <span>
              {o.label}
              {o.hint ? <span className="muted small block">{o.hint}</span> : null}
            </span>
          </label>
        ))}
        <FieldError id="d-decision-err" message={fe.decision} />
      </fieldset>
      {decision === "override" ? (
        <div className="field">
          <label htmlFor="d-override">Priority level to apply</label>
          <select id="d-override" value={override} onChange={(e) => setOverride(e.target.value)} aria-invalid={!!fe.override_priority} aria-describedby="d-override-err">
            <option value="">Select…</option>
            {[...r.priority_levels]
              .sort((a, b) => a.rank - b.rank)
              .map((l) => (
                <option key={l.code} value={l.code}>
                  {l.code} — {l.label} (rank {l.rank})
                </option>
              ))}
          </select>
          {r.priority_levels.length === 0 ? <p className="field-error">The protocol's priority levels could not be loaded.</p> : null}
          <FieldError id="d-override-err" message={fe.override_priority} />
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="d-rationale">Rationale (required)</label>
        <textarea
          id="d-rationale"
          rows={3}
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          required
          aria-invalid={!!fe.rationale}
          aria-describedby="d-rationale-err"
        />
        <FieldError id="d-rationale-err" message={fe.rationale} />
      </div>
      {m.error && Object.keys(m.error.fieldErrors).length === 0 ? <ErrorBox error={m.error} title="Decision not recorded" /> : null}
      <button type="submit" className="btn btn-primary" disabled={m.busy}>
        {m.busy ? "Recording…" : "Record decision"}
      </button>
    </form>
  );
}

function ActionPanel({ r, reload, following }: { r: ReviewDetail; reload: () => void; following: boolean }) {
  const { can } = useAuth();
  const m = useMutation();
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const a = r.action;
  const showRetry = can("review:decide") && (r.status === "EXECUTION_FAILED" || (r.status === "APPROVED" && !following));

  async function retry() {
    const res = await m.run(() => api.execute(r.id));
    if (res) {
      setResult(res);
      reload();
    }
  }

  if (!a && !showRetry) return null;
  return (
    <section className="card" aria-label="Action and verification">
      <h2>Synthetic queue action and verification</h2>
      {!a ? (
        <p className="muted">No action has been executed yet.</p>
      ) : (
        <dl className="kv">
          <div>
            <dt>Action</dt>
            <dd>
              <span className="mono">{a.id}</span> — {humanize(a.action_type)} <StatusBadge status={a.status === "SUCCEEDED" ? "success" : "failure"} />
            </dd>
          </div>
          <div>
            <dt>Executed</dt>
            <dd>
              {fmtTime(a.executed_at)} by {a.executed_by}
            </dd>
          </div>
          <div>
            <dt>Verified</dt>
            <dd>{a.verified ? <Badge tone="ok">✓ Verified by read-back</Badge> : <Badge tone="danger">✕ Not verified</Badge>}</dd>
          </div>
          <div>
            <dt>Expected priority</dt>
            <dd>
              <strong>{a.verification?.expected_priority ?? "—"}</strong>
            </dd>
          </div>
          <div>
            <dt>Observed in synthetic queue</dt>
            <dd>
              <strong>{a.verification?.observed_priority ?? "—"}</strong>
              {a.verification?.verified_at ? <span className="muted small"> at {fmtTime(a.verification.verified_at)}</span> : null}
            </dd>
          </div>
          {a.error ? (
            <div>
              <dt>Error</dt>
              <dd className="field-error">{a.error}</dd>
            </div>
          ) : null}
        </dl>
      )}
      {showRetry ? (
        <>
          {r.status === "EXECUTION_FAILED" ? (
            <p className="field-error">The approved action failed or could not be verified. The synthetic queue has not been reported as updated.</p>
          ) : (
            <p className="muted">The approved action has not been applied yet.</p>
          )}
          <button type="button" className="btn btn-primary" onClick={() => void retry()} disabled={m.busy}>
            {m.busy ? "Retrying…" : "Retry action"}
          </button>
        </>
      ) : null}
      {m.error ? <ErrorBox error={m.error} title="Action not applied" /> : null}
      {result ? (
        <p className={result.status === "EXECUTED" ? "success" : "field-error"} role="status">
          Result: {result.status.replace(/_/g, " ")}
          {result.duplicate ? " (already applied — duplicate suppressed)" : ""}
          {result.error ? ` — ${result.error}` : ""}
        </p>
      ) : null}
    </section>
  );
}
