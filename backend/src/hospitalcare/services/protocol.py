"""Versioned triage protocols: loading, validation and deterministic evaluation (FR-008..FR-011).

The engine applies only rules written in a protocol file. It never supplies a
threshold of its own, never uses historical records as criterion evidence, and
returns an explicit unresolved status whenever evidence is missing, unverified
or conflicting.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from ..config import get_settings
from ..db import utcnow

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,63}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

URGENT_MESSAGE = (
    "A configured escalation criterion is met. Direct this patient to immediate clinical review now using the "
    "facility's established process. Do not wait for this system."
)
REVIEW_REASON = (
    "This is a proposal only. An authorized nurse or clinician must review the evidence and decide; "
    "nothing changes until they do."
)
HISTORY_NOTE = "Historical records are shown as context only and are never used as evidence for protocol criteria."


class ProtocolError(Exception):
    """Base class for protocol problems; `status` is the evaluation status to report."""

    status = "PROTOCOL_UNAVAILABLE"


class ProtocolUnavailable(ProtocolError):
    status = "PROTOCOL_UNAVAILABLE"


class ProtocolNotApproved(ProtocolError):
    status = "PROTOCOL_NOT_APPROVED"


class Criterion(BaseModel):
    field: str
    op: Literal["lt", "le", "gt", "ge", "eq", "ne", "in"]
    value: Any


class Rule(BaseModel):
    rule_id: str
    priority: str
    description: str
    escalation: bool = False
    match: Literal["all", "any"] = "all"
    criteria: list[Criterion] = Field(min_length=1)


class EvidenceField(BaseModel):
    kind: Literal["observation", "symptom"]
    type: Literal["number", "text", "boolean"]
    unit: str | None = None
    requires_verification: bool = True


class PriorityLevel(BaseModel):
    code: str
    rank: int
    label: str


class Approval(BaseModel):
    approved_by: str | None = None
    approved_on: str | None = None
    approval_reference: str | None = None


class DefaultPriority(BaseModel):
    priority: str
    description: str


class Protocol(BaseModel):
    protocol_id: str
    version: str
    title: str
    status: Literal["approved", "synthetic_demo", "draft", "retired"]
    disclaimer: str | None = None
    source: str
    approval: Approval = Approval()
    priority_levels: list[PriorityLevel] = Field(min_length=1)
    evidence_fields: dict[str, EvidenceField]
    required_fields: list[str]
    rules: list[Rule] = Field(min_length=1)
    default_priority: DefaultPriority | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Protocol:
        if not ID_RE.match(self.protocol_id) or not VERSION_RE.match(self.version):
            raise ValueError("invalid protocol_id or version format")
        codes = {p.code for p in self.priority_levels}
        if len(codes) != len(self.priority_levels) or len({p.rank for p in self.priority_levels}) != len(codes):
            raise ValueError("priority level codes and ranks must be unique")
        if len({r.rule_id for r in self.rules}) != len(self.rules):
            raise ValueError("rule_id values must be unique")
        for f in self.required_fields:
            if f not in self.evidence_fields:
                raise ValueError(f"required field '{f}' is not declared in evidence_fields")
        for r in self.rules:
            if r.priority not in codes:
                raise ValueError(f"rule {r.rule_id} uses undefined priority '{r.priority}'")
            for c in r.criteria:
                if c.field not in self.evidence_fields:
                    raise ValueError(f"rule {r.rule_id} uses undeclared field '{c.field}'")
        if self.default_priority and self.default_priority.priority not in codes:
            raise ValueError("default_priority uses undefined priority")
        if self.status == "approved" and not (self.approval.approved_by and self.approval.approved_on):
            raise ValueError("approved protocols must record approval.approved_by and approval.approved_on")
        return self

    def level(self, code: str) -> PriorityLevel:
        return next(p for p in self.priority_levels if p.code == code)


class LoadedProtocol(BaseModel):
    protocol: Protocol
    sha256: str
    path: str


def protocol_filename(protocol_id: str, version: str) -> str:
    if not ID_RE.match(protocol_id) or not VERSION_RE.match(version):
        raise ProtocolUnavailable("invalid protocol identifier or version")
    return f"{protocol_id}_v{version}.yaml"


def parse_protocol(raw: bytes, path: str = "<memory>") -> LoadedProtocol:
    try:
        data = yaml.safe_load(raw)
        protocol = Protocol.model_validate(data)
    except (yaml.YAMLError, ValidationError, TypeError) as exc:
        raise ProtocolUnavailable(f"protocol failed validation: {exc}") from exc
    return LoadedProtocol(protocol=protocol, sha256=hashlib.sha256(raw).hexdigest(), path=path)


def load_protocol(protocol_id: str, version: str, directory: Path | None = None) -> LoadedProtocol:
    directory = directory or get_settings().protocols_path
    path = directory / protocol_filename(protocol_id, version)
    if not path.is_file():
        raise ProtocolUnavailable(f"protocol {protocol_id} v{version} is not configured")
    loaded = parse_protocol(path.read_bytes(), str(path.name))
    p = loaded.protocol
    if (p.protocol_id, p.version) != (protocol_id, version):
        raise ProtocolUnavailable("protocol file contents do not match the requested id/version")
    return loaded


def list_protocols(directory: Path | None = None) -> list[dict[str, Any]]:
    directory = directory or get_settings().protocols_path
    result = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            loaded = parse_protocol(path.read_bytes(), path.name)
            p = loaded.protocol
            result.append({"protocol_id": p.protocol_id, "version": p.version, "title": p.title,
                           "status": p.status, "evaluable": is_evaluable(p), "sha256": loaded.sha256,
                           "disclaimer": p.disclaimer, "valid": True, "file": path.name,
                           "priority_levels": [lvl.model_dump() for lvl in p.priority_levels]})
        except ProtocolError as exc:
            result.append({"file": path.name, "valid": False, "error": str(exc)[:300], "evaluable": False})
    return result


def is_evaluable(protocol: Protocol) -> bool:
    return protocol.status == "approved" or (protocol.status == "synthetic_demo" and get_settings().demo_mode)


# --- Evidence resolution ---------------------------------------------------------------


def _obs_evidence(o: dict) -> dict[str, Any]:
    return {"value": o["value_num"] if o["value_num"] is not None else o["value_text"], "unit": o["unit"],
            "observation_id": o["id"], "source_type": o["source_type"],
            "verification_status": o["verification_status"], "recorded_by": o["recorded_by"],
            "recorded_at": o["recorded_at"]}


def resolve_evidence(protocol: Protocol, observations: list[dict], symptoms: list[dict]):
    """Return (evidence, missing, conflicts) for every declared field."""
    evidence: dict[str, dict] = {}
    missing: list[dict] = []
    conflicts: list[dict] = []
    for name, spec in protocol.evidence_fields.items():
        if spec.kind == "observation":
            active = [o for o in observations if o["code"] == name and o["status"] == "active"]
            if len({(o["value_num"], o["value_text"]) for o in active}) > 1:
                conflicts.append({"field": name, "values": [_obs_evidence(o) for o in active]})
                continue
            eligible = [o for o in active if o["verification_status"] == "verified" or not spec.requires_verification]
            if not active:
                missing.append({"field": name, "reason": "not recorded for this encounter"})
            elif not eligible:
                missing.append({"field": name, "reason": "recorded but not verified",
                                "observation_ids": [o["id"] for o in active]})
            else:
                evidence[name] = _obs_evidence(eligible[-1])
        else:
            items = [s for s in symptoms if s["code"] == name]
            if len({s["present"] for s in items}) > 1:
                conflicts.append({"field": name, "values": [
                    {"value": bool(s["present"]), "symptom_id": s["id"], "source_type": s["source_type"],
                     "recorded_at": s["recorded_at"]} for s in items]})
            elif not items:
                missing.append({"field": name, "reason": "not documented (absence has not been assumed)"})
            else:
                s = items[-1]
                evidence[name] = {"value": bool(s["present"]), "symptom_id": s["id"], "source_type": s["source_type"],
                                  "provenance": "patient_reported" if s["source_type"] == "patient_reported"
                                  else "clinically_recorded", "recorded_by": s["recorded_by"],
                                  "recorded_at": s["recorded_at"]}
    return evidence, missing, conflicts


def _compare(op: str, actual: Any, expected: Any) -> bool:
    if op == "in":
        return actual in expected
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return False
    return {"lt": actual < expected, "le": actual <= expected, "gt": actual > expected,
            "ge": actual >= expected}[op]


def _evaluate_rule(rule: Rule, evidence: dict[str, dict]) -> tuple[str, list[dict], list[str]]:
    """Return (state, satisfied criteria, missing fields). state: matched | not_matched | undetermined."""
    satisfied, missing_fields = [], []
    for c in rule.criteria:
        if c.field not in evidence:
            missing_fields.append(c.field)
            continue
        if _compare(c.op, evidence[c.field]["value"], c.value):
            satisfied.append({"field": c.field, "op": c.op, "value": c.value, "evidence": evidence[c.field]})
    if rule.match == "any":
        if satisfied:
            return "matched", satisfied, missing_fields
        return ("undetermined" if missing_fields else "not_matched"), [], missing_fields
    if missing_fields:
        return "undetermined", satisfied, missing_fields
    return ("matched" if len(satisfied) == len(rule.criteria) else "not_matched"), satisfied, []


def _unresolved(protocol_id: str, version: str, status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "protocol_id": protocol_id, "protocol_version": version, "protocol_sha256": extra.get("sha256"),
        "protocol_status": extra.get("protocol_status"), "protocol_title": extra.get("title"),
        "is_clinical_protocol": False, "disclaimer": extra.get("disclaimer"),
        "status": status, "status_reason": reason, "proposed_priority": None, "proposed_priority_label": None,
        "proposed_priority_rank": None, "urgent_flag": False, "urgent_message": None, "matched_rules": [],
        "undetermined_rules": [], "evidence_used": {}, "missing_information": [], "conflicts": [],
        "historical_context_used": False, "history_note": HISTORY_NOTE, "review_required": True,
        "review_reason": REVIEW_REASON, "evaluated_at": utcnow(),
    }


def evaluate(protocol_id: str, version: str, observations: list[dict], symptoms: list[dict],
             directory: Path | None = None) -> dict[str, Any]:
    """Deterministically evaluate current-encounter evidence against a configured protocol."""
    try:
        loaded = load_protocol(protocol_id, version, directory)
    except ProtocolError as exc:
        return _unresolved(protocol_id, version, exc.status, str(exc))
    p = loaded.protocol
    meta = {"sha256": loaded.sha256, "protocol_status": p.status, "title": p.title, "disclaimer": p.disclaimer}
    if not is_evaluable(p):
        why = ("synthetic_demo protocols are evaluated only when HCAI_DEMO_MODE=true" if p.status == "synthetic_demo"
               else f"protocol status is '{p.status}'; only approved protocols are evaluated")
        return _unresolved(protocol_id, version, "PROTOCOL_NOT_APPROVED", why, **meta)

    evidence, missing, conflicts = resolve_evidence(p, observations, symptoms)
    matched, undetermined = [], []
    for rule in p.rules:
        state, satisfied, missing_fields = _evaluate_rule(rule, evidence)
        level = p.level(rule.priority)
        if state == "matched":
            matched.append({"rule_id": rule.rule_id, "priority": rule.priority, "rank": level.rank,
                            "description": rule.description, "escalation": rule.escalation,
                            "match": rule.match, "criteria_met": satisfied})
        elif state == "undetermined":
            undetermined.append({"rule_id": rule.rule_id, "priority": rule.priority, "rank": level.rank,
                                 "missing_or_conflicting_fields": missing_fields})

    result = _unresolved(protocol_id, version, "NO_RULE_MATCHED", "", **meta)
    result.update(is_clinical_protocol=p.status == "approved", matched_rules=matched,
                  undetermined_rules=undetermined, evidence_used=evidence, missing_information=missing,
                  conflicts=conflicts)
    if any(r["escalation"] for r in matched):
        result.update(urgent_flag=True, urgent_message=URGENT_MESSAGE)

    missing_required = [m for m in missing if m["field"] in p.required_fields]
    best = min(matched, key=lambda r: r["rank"]) if matched else None
    higher_undetermined = [u for u in undetermined if best is None or u["rank"] < best["rank"]]

    if conflicts:
        result.update(status="CONFLICTING_EVIDENCE",
                      status_reason="Conflicting values must be verified before a priority can be proposed.")
    elif missing_required:
        result.update(status="INSUFFICIENT_EVIDENCE",
                      status_reason="Required evidence is missing or unverified: "
                                    + ", ".join(m["field"] for m in missing_required))
    elif higher_undetermined:
        result.update(status="INSUFFICIENT_EVIDENCE",
                      status_reason="A higher-priority rule could not be evaluated because evidence is missing.")
    elif best:
        level = p.level(best["priority"])
        result.update(status="PROPOSED", status_reason=f"Highest-ranked matched rule: {best['rule_id']}",
                      proposed_priority=level.code, proposed_priority_label=level.label,
                      proposed_priority_rank=level.rank)
    elif p.default_priority:
        level = p.level(p.default_priority.priority)
        result["matched_rules"] = [{
            "rule_id": "DEFAULT", "priority": level.code, "rank": level.rank,
            "description": p.default_priority.description, "escalation": False, "match": "all",
            "criteria_met": [{"field": f, "op": "present", "value": None, "evidence": evidence[f]}
                             for f in p.required_fields],
        }]
        result.update(status="PROPOSED", status_reason="No rule matched; protocol default applies.",
                      proposed_priority=level.code, proposed_priority_label=level.label,
                      proposed_priority_rank=level.rank)
    else:
        result["status_reason"] = "No protocol rule matched and the protocol defines no default."
    return result
