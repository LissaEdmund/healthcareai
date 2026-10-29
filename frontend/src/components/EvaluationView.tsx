import type { EvaluationResult } from "../api";
import { fmtOp, fmtTime, fmtValue, humanize, shortHash } from "../format";
import { Badge, StatusBadge } from "./Badge";
import { ConflictList, EvidenceDetail, MissingList } from "./Clinical";

export function UrgentAlert({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div className="urgent-alert" role="alert">
      <strong>
        <span aria-hidden="true">⚠ </span>URGENT — escalation criterion met
      </strong>
      <p>{message}</p>
    </div>
  );
}

export function SyntheticProtocolLabel({ protocolStatus }: { protocolStatus: string | null | undefined }) {
  if (protocolStatus !== "synthetic_demo") return null;
  return (
    <div className="synthetic-protocol-label" role="note">
      SYNTHETIC DEMO PROTOCOL — NOT A CLINICAL PRIORITY
    </div>
  );
}

/** Deterministic protocol evaluation with its evidence. A proposal only, never a decision. */
export function EvaluationView({ evaluation }: { evaluation: EvaluationResult }) {
  const e = evaluation;
  return (
    <section className="evaluation" aria-label="Protocol evaluation">
      <h2>Protocol evaluation (proposal)</h2>
      <SyntheticProtocolLabel protocolStatus={e.protocol_status} />

      <div className="card">
        <dl className="kv">
          <div>
            <dt>Protocol</dt>
            <dd>
              <span className="mono">{e.protocol_id}</span> v{e.protocol_version}
              {e.protocol_title ? <span className="muted"> — {e.protocol_title}</span> : null}
            </dd>
          </div>
          <div>
            <dt>SHA-256</dt>
            <dd className="mono" title={e.protocol_sha256 ?? undefined}>
              {shortHash(e.protocol_sha256, 16)}
            </dd>
          </div>
          <div>
            <dt>Protocol status</dt>
            <dd>
              <Badge tone={e.protocol_status === "approved" ? "ok" : "synthetic"}>{e.protocol_status ?? "unknown"}</Badge>
            </dd>
          </div>
          <div>
            <dt>Evaluation status</dt>
            <dd>
              <StatusBadge status={e.status} />
              {e.status_reason ? <div className="muted small">{e.status_reason}</div> : null}
            </dd>
          </div>
          <div>
            <dt>Proposed priority</dt>
            <dd>
              {e.proposed_priority ? (
                <>
                  <strong className="priority">{e.proposed_priority}</strong>
                  {e.proposed_priority_label ? ` — ${e.proposed_priority_label}` : ""}{" "}
                  <Badge tone="warn">Proposal — requires nurse review</Badge>
                </>
              ) : (
                <span>No priority proposed</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Escalation</dt>
            <dd>
              {e.urgent_flag ? (
                <Badge tone="danger">
                  <span aria-hidden="true">⚠ </span>Escalation criterion met
                </Badge>
              ) : (
                <span>No escalation criterion met</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Evaluated</dt>
            <dd>{fmtTime(e.evaluated_at)}</dd>
          </div>
        </dl>
        {e.disclaimer ? (
          <p className="disclaimer">
            <strong>Disclaimer:</strong> {e.disclaimer}
          </p>
        ) : null}
      </div>

      <h3>Matched rules ({e.matched_rules.length})</h3>
      {e.matched_rules.length === 0 ? (
        <p className="muted">No protocol rule matched the recorded evidence.</p>
      ) : (
        <ul className="plain-list">
          {e.matched_rules.map((r) => (
            <li key={r.rule_id} className="card rule">
              <div className="rule-head">
                <span className="mono">{r.rule_id}</span> → <strong>{r.priority}</strong>{" "}
                {r.escalation ? <Badge tone="danger">Escalation rule</Badge> : null}
                <span className="muted small"> (match: {r.match})</span>
              </div>
              <p>{r.description}</p>
              <ul className="plain-list criteria">
                {r.criteria_met.map((c, i) => (
                  <li key={i}>
                    <div className="criterion">
                      Criterion: <strong>{humanize(c.field)}</strong> {fmtOp(c.op)} {c.value === null ? "" : fmtValue(c.value)}
                    </div>
                    <EvidenceDetail ev={c.evidence} />
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}

      {e.undetermined_rules && e.undetermined_rules.length > 0 ? (
        <>
          <h3>Rules that could not be evaluated ({e.undetermined_rules.length})</h3>
          <ul>
            {e.undetermined_rules.map((u) => (
              <li key={u.rule_id}>
                <span className="mono">{u.rule_id}</span> ({u.priority}) — missing or conflicting:{" "}
                {u.missing_or_conflicting_fields.map(humanize).join(", ")}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <MissingList items={e.missing_information} title="Missing information (evaluation)" />
      <ConflictList conflicts={e.conflicts} title="Conflicting evidence (evaluation)" />

      <div className="card notes">
        <p>
          <strong>History:</strong> {e.history_note}
        </p>
        <p>
          <strong>Review required:</strong> {e.review_reason}
        </p>
      </div>
    </section>
  );
}
