"""Patient-context retrieval (FR-006, FR-007).

Returns only database facts with provenance. Nothing is inferred or filled in:
absent data is reported as missing, differing values as conflicts.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .. import repositories as repo
from ..catalog import OBSERVATION_CODES, SYMPTOM_CODES
from ..config import get_settings
from ..db import utcnow
from ..security import Principal

CATEGORIES = ("demographics", "current_encounter", "history", "record_sources")
# Shown as "not recorded" when absent so staff can see completeness at a glance.
CORE_OBSERVATION_CODES = ("temperature_c", "heart_rate_bpm", "resp_rate_bpm", "spo2_pct", "systolic_bp_mmhg", "avpu")
RECURRENCE_STATEMENT = (
    "Recurrence of a documented complaint does not by itself indicate that previous treatment failed "
    "or that an earlier assessment was wrong. Review the documented outcomes below."
)
MISSING_RECORD_STATEMENT = "Not available in the records searched; this does not mean it did not happen."


def _provenance(source_type: str) -> str:
    return "patient_reported" if source_type == "patient_reported" else "clinically_recorded"


def _obs_item(o: dict) -> dict[str, Any]:
    meta = OBSERVATION_CODES.get(o["code"], {})
    return {
        "id": o["id"],
        "code": o["code"],
        "label": meta.get("label", o["code"]),
        "value": o["value_num"] if o["value_num"] is not None else o["value_text"],
        "unit": o["unit"],
        "source_type": o["source_type"],
        "provenance": _provenance(o["source_type"]),
        "verification_status": o["verification_status"],
        "status": o["status"],
        "source_ref": o["source_ref"],
        "recorded_by": o["recorded_by"],
        "recorded_at": o["recorded_at"],
    }


def find_observation_conflicts(observations: list[dict]) -> list[dict[str, Any]]:
    """Active observations of the same code with differing values are conflicts."""
    by_code: dict[str, list[dict]] = {}
    for o in observations:
        if o["status"] == "active":
            by_code.setdefault(o["code"], []).append(o)
    conflicts = []
    for code, items in by_code.items():
        values = {(i["value_num"], i["value_text"]) for i in items}
        if len(values) > 1:
            conflicts.append({
                "field": code,
                "scope": "current_encounter",
                "message": "Differing values recorded; an authorized staff member must verify one value and "
                           "supersede the others.",
                "values": [_obs_item(i) for i in items],
            })
    return conflicts


def _history_conflicts(notes: list[dict]) -> list[dict[str, Any]]:
    allergy = [n for n in notes if n["category"] == "allergy"]
    by_source: dict[str, set[str]] = {}
    for n in allergy:
        by_source.setdefault(n["source_type"], set()).add(n["content"].strip().lower())
    if len(by_source) > 1 and len({frozenset(v) for v in by_source.values()}) > 1:
        return [{
            "field": "allergy",
            "scope": "history",
            "message": "Allergy documentation differs between record sources; verify with the patient and the "
                       "original records.",
            "values": [{"id": n["id"], "value": n["content"], "source_type": n["source_type"],
                        "source_ref": n["source_ref"], "recorded_at": n["recorded_at"]} for n in allergy],
        }]
    return []


def build_patient_context(conn: sqlite3.Connection, principal: Principal, patient_id: str, encounter_id: str,
                          categories: list[str] | None = None) -> dict[str, Any]:
    requested = list(categories or CATEGORIES)
    unknown = set(requested) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"unknown categories: {sorted(unknown)}")

    patient = repo.get_patient(conn, patient_id)
    encounter = repo.get_encounter(conn, encounter_id)
    if encounter["patient_id"] != patient_id:
        raise ValueError("encounter does not belong to this patient")

    withheld: list[str] = []
    allowed = []
    for cat in requested:
        needed = "patient:read_basic" if cat in ("demographics", "record_sources") else "patient:read_history"
        if cat == "current_encounter" and not principal.can("patient:read_history"):
            needed = "patient:read_basic"  # complaint only; observations withheld below
        (allowed if principal.can(needed) else withheld).append(cat)
    can_clinical = principal.can("patient:read_history")

    ctx: dict[str, Any] = {
        "data_label": "SYNTHETIC — not a real patient",
        "generated_at": utcnow(),
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "categories_returned": allowed,
        "categories_withheld": withheld,
        "missing_information": [],
        "conflicts": [],
    }

    if "demographics" in allowed:
        ctx["patient"] = {
            "id": patient["id"],
            "display_name": f"{patient['given_name']} {patient['family_name']}",
            "sex": patient["sex"],
            "birth_year": patient["birth_year"],
            "is_synthetic": bool(patient["is_synthetic"]),
        }

    if "record_sources" in allowed:
        sources = repo.list_record_sources(conn, patient_id)
        ctx["record_sources"] = sources
        for s in sources:
            if s["status"] != "available":
                ctx["missing_information"].append({
                    "item": f"{s['source_type']} ({s['status']})",
                    "detail": f"{s['note'] or ''} {MISSING_RECORD_STATEMENT}".strip(),
                })

    if "current_encounter" in allowed:
        ctx["encounter"] = {
            "id": encounter["id"],
            "arrived_at": encounter["arrived_at"],
            "department": encounter["department"],
            "complaint_code": encounter["complaint_code"],
            "chief_complaint": encounter["chief_complaint"],
            "complaint_source": encounter["complaint_source"],
            "complaint_provenance": _provenance(encounter["complaint_source"]),
            "status": encounter["status"],
        }
        if can_clinical:
            obs = repo.observations_for_encounters(conn, [encounter_id])
            ctx["current_observations"] = [_obs_item(o) for o in obs]
            ctx["current_symptoms"] = [
                {"id": s["id"], "code": s["code"], "label": SYMPTOM_CODES.get(s["code"], s["code"]),
                 "present": bool(s["present"]), "source_type": s["source_type"],
                 "provenance": _provenance(s["source_type"]), "recorded_by": s["recorded_by"],
                 "recorded_at": s["recorded_at"]}
                for s in repo.symptoms_for_encounter(conn, encounter_id)
            ]
            active_codes = {o["code"] for o in obs if o["status"] == "active"}
            for code in CORE_OBSERVATION_CODES:
                if code not in active_codes:
                    ctx["missing_information"].append({
                        "item": f"current observation: {OBSERVATION_CODES[code]['label']}",
                        "detail": "Not recorded for this encounter. No value has been assumed.",
                    })
            for o in obs:
                if o["status"] == "active" and o["verification_status"] != "verified":
                    ctx["missing_information"].append({
                        "item": f"verification: {OBSERVATION_CODES.get(o['code'], {}).get('label', o['code'])}",
                        "detail": f"Observation {o['id']} is recorded but unverified.",
                    })
            ctx["conflicts"].extend(find_observation_conflicts(obs))

    if "history" in allowed:
        prior = repo.prior_encounters(conn, patient_id, encounter["arrived_at"], encounter_id)
        prior_ids = [p["id"] for p in prior]
        notes = repo.notes_for_encounters(conn, prior_ids)
        obs = repo.observations_for_encounters(conn, prior_ids)
        history = []
        for p in prior:
            history.append({
                "id": p["id"],
                "arrived_at": p["arrived_at"],
                "complaint_code": p["complaint_code"],
                "chief_complaint": p["chief_complaint"],
                "record_source": p["record_source"],
                "notes": [
                    {"id": n["id"], "category": n["category"], "content": n["content"],
                     "source_type": n["source_type"], "provenance": _provenance(n["source_type"]),
                     "source_ref": n["source_ref"], "recorded_by": n["recorded_by"],
                     "recorded_at": n["recorded_at"]}
                    for n in notes if n["encounter_id"] == p["id"]
                ],
                "observations": [_obs_item(o) for o in obs if o["encounter_id"] == p["id"]],
            })
        ctx["previous_encounters"] = history
        if not prior:
            ctx["missing_information"].append({
                "item": "previous encounters",
                "detail": f"No previous encounters found in the searched records. {MISSING_RECORD_STATEMENT}",
            })

        lookback = get_settings().recurrence_lookback_days
        cutoff = (datetime.fromisoformat(encounter["arrived_at"]) - timedelta(days=lookback)).isoformat()
        same = [p for p in prior if p["complaint_code"] == encounter["complaint_code"] and p["arrived_at"] >= cutoff
                and encounter["complaint_code"] not in ("other", "follow_up")]
        ctx["recurring_complaint"] = {
            "detected": bool(same),
            "complaint_code": encounter["complaint_code"],
            "lookback_days": lookback,
            "prior_encounter_ids": [p["id"] for p in same],
            "statement": RECURRENCE_STATEMENT if same else None,
        }
        ctx["conflicts"].extend(_history_conflicts(notes))

    return ctx
