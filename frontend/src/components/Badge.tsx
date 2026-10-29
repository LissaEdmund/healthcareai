import type { ReactNode } from "react";

export type Tone = "neutral" | "info" | "ok" | "warn" | "danger" | "ai" | "synthetic";

/** Status is always conveyed as text; colour is supplementary. */
export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  // reviews
  PENDING: "warn",
  APPROVED: "info",
  EXECUTED: "ok",
  REJECTED: "neutral",
  CLARIFICATION_REQUESTED: "warn",
  EXECUTION_FAILED: "danger",
  // workflow runs
  RUNNING: "info",
  AWAITING_REVIEW: "warn",
  COMPLETED: "ok",
  REJECTED_NO_ACTION: "neutral",
  ACTION_FAILED: "danger",
  VALIDATION_FAILED: "danger",
  CONTEXT_UNAVAILABLE: "danger",
  EVALUATION_FAILED: "danger",
  REVIEW_CREATION_FAILED: "danger",
  ERROR: "danger",
  // evaluations
  PROPOSED: "info",
  INSUFFICIENT_EVIDENCE: "warn",
  CONFLICTING_EVIDENCE: "danger",
  NO_RULE_MATCHED: "neutral",
  PROTOCOL_UNAVAILABLE: "danger",
  PROTOCOL_NOT_APPROVED: "danger",
  // steps
  ok: "ok",
  failed: "danger",
  degraded: "warn",
  // observations / outcomes
  verified: "ok",
  unverified: "warn",
  active: "ok",
  superseded: "neutral",
  entered_in_error: "danger",
  success: "ok",
  failure: "danger",
  denied: "danger",
  info: "neutral",
  open: "info",
  closed: "neutral",
  // summaries
  GENERATED: "ai",
  MODEL_UNAVAILABLE: "warn",
  GUARD_REJECTED: "warn",
};

export function StatusBadge({ status, prefix }: { status: string | null | undefined; prefix?: string }) {
  if (!status) return <Badge>—</Badge>;
  const icon = { ok: "✓", danger: "✕", warn: "!", info: "•", neutral: "–", ai: "AI", synthetic: "" }[STATUS_TONES[status] ?? "neutral"];
  return (
    <Badge tone={STATUS_TONES[status] ?? "neutral"}>
      {icon ? <span aria-hidden="true">{icon} </span> : null}
      {prefix ? `${prefix}: ` : ""}
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

export function ProvenanceBadge({ sourceType, provenance }: { sourceType?: string | null; provenance?: string | null }) {
  const prov = provenance ?? (sourceType === "patient_reported" ? "patient_reported" : sourceType ? "clinically_recorded" : null);
  if (!prov) return null;
  return prov === "patient_reported" ? (
    <Badge tone="warn" title="Reported by the patient; not clinically recorded">Patient-reported</Badge>
  ) : (
    <Badge tone="info" title="Clinically recorded or documented">Clinically recorded</Badge>
  );
}

export function UrgentBadge() {
  return (
    <Badge tone="danger">
      <span aria-hidden="true">⚠ </span>URGENT — escalation criterion met
    </Badge>
  );
}
