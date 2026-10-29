"""Synthetic demonstration data. Every person and record here is fictional ("Mfano" is Swahili for "example")."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from . import audit
from . import repositories as repo
from .config import get_settings
from .db import transaction
from .security import hash_password

DEMO_USERS = [
    ("USR-intake", "intake.demo", "Synthetic Intake Clerk", "intake_clerk"),
    ("USR-nurse1", "nurse.demo", "Synthetic Nurse A", "nurse"),
    ("USR-nurse2", "nurse2.demo", "Synthetic Nurse B", "nurse"),
    ("USR-clin1", "clinician.demo", "Synthetic Clinician", "clinician"),
    ("USR-audit", "auditor.demo", "Synthetic Auditor", "auditor"),
    ("USR-admin", "admin.demo", "Synthetic Administrator", "admin"),
]


def _ago(**kw) -> str:
    return (datetime.now(UTC) - timedelta(**kw)).isoformat(timespec="seconds")


def _vitals(conn, enc: str, values: dict, *, verified: bool = True, source: str = "clinician_measured",
            by: str = "USR-nurse1", at: str | None = None) -> None:
    from .catalog import OBSERVATION_CODES

    for code, value in values.items():
        num = value if isinstance(value, (int, float)) else None
        txt = value if isinstance(value, str) else None
        repo.add_observation(conn, enc, code, value_num=num, value_text=txt, unit=OBSERVATION_CODES[code]["unit"],
                             source_type=source, verification_status="verified" if verified else "unverified",
                             recorded_by=by, recorded_at=at)


def _symptoms(conn, enc: str, present: list[str], absent: list[str], at: str | None = None) -> None:
    for code in present:
        repo.add_symptom(conn, enc, code, True, "patient_reported", "USR-intake", at)
    for code in absent:
        repo.add_symptom(conn, enc, code, False, "patient_reported", "USR-intake", at)


SCREEN = ["chest_pain", "difficulty_breathing", "convulsion"]
NORMALISH = {"temperature_c": 37.2, "heart_rate_bpm": 84, "resp_rate_bpm": 18, "spo2_pct": 97, "avpu": "A",
             "systolic_bp_mmhg": 124}


def seed(conn: sqlite3.Connection) -> dict[str, int]:
    settings = get_settings()
    fac = settings.facility_code
    pw = hash_password(settings.demo_password)
    with transaction(conn):
        for uid, username, name, role in DEMO_USERS:
            repo.create_user(conn, username, name, role, pw, user_id=uid)

        # 1. Complete encounter with a documented recurring complaint (demo happy path).
        p1 = repo.create_patient(conn, "Asha", "Mfano", "female", 1988, "USR-intake", patient_id="SYN-P-0001")
        repo.upsert_record_source(conn, p1, "electronic_record", "available", None)
        repo.upsert_record_source(conn, p1, "paper_record", "available", "Paper file transcribed 2026-02")
        h1 = repo.create_encounter(conn, p1, fac, "headache", "Headache for three days", "USR-intake",
                                   arrived_at=_ago(days=120), status="closed", record_source="paper_record_transcribed",
                                   encounter_id="SYN-E-0001-H1")
        repo.add_note(conn, h1, "documented_assessment", "Tension-type headache documented by clinician",
                      "paper_record_transcribed", source_ref="Paper file p.4", recorded_by="historic", recorded_at=_ago(days=120))
        repo.add_note(conn, h1, "documented_treatment", "Paracetamol documented as given",
                      "paper_record_transcribed", source_ref="Paper file p.4", recorded_by="historic", recorded_at=_ago(days=120))
        repo.add_note(conn, h1, "outcome", "Discharged home; advised to return if worse",
                      "paper_record_transcribed", source_ref="Paper file p.4", recorded_by="historic", recorded_at=_ago(days=120))
        _vitals(conn, h1, {"temperature_c": 36.9, "systolic_bp_mmhg": 128}, source="paper_record_transcribed",
                by="historic", at=_ago(days=120))
        h2 = repo.create_encounter(conn, p1, fac, "headache", "Headache recurring, worse in mornings", "USR-intake",
                                   arrived_at=_ago(days=35), status="closed", encounter_id="SYN-E-0001-H2")
        repo.add_note(conn, h2, "result", "Blood pressure re-check 131/84 mmHg documented", "electronic_record",
                      source_ref="EMR visit note", recorded_by="historic", recorded_at=_ago(days=35))
        repo.add_note(conn, h2, "outcome", "Follow-up planned in 4 weeks", "electronic_record",
                      source_ref="EMR visit note", recorded_by="historic", recorded_at=_ago(days=35))
        repo.add_note(conn, h2, "allergy", "No known drug allergies", "electronic_record",
                      source_ref="EMR allergy list", recorded_by="historic", recorded_at=_ago(days=35))
        e1 = repo.create_encounter(conn, p1, fac, "headache", "Headache again since yesterday", "USR-intake",
                                   arrived_at=_ago(minutes=25), encounter_id="SYN-E-0001")
        _vitals(conn, e1, NORMALISH)
        _symptoms(conn, e1, ["headache"], SCREEN)

        # 2. Missing vital sign (no SpO2 recorded) and an unverified heart rate.
        p2 = repo.create_patient(conn, "Baraka", "Mfano", "male", 1975, "USR-intake", patient_id="SYN-P-0002")
        repo.upsert_record_source(conn, p2, "electronic_record", "available", None)
        e2 = repo.create_encounter(conn, p2, fac, "cough", "Cough for one week", "USR-intake",
                                   arrived_at=_ago(minutes=18), encounter_id="SYN-E-0002")
        _vitals(conn, e2, {"temperature_c": 37.8, "resp_rate_bpm": 22, "avpu": "A"})
        _vitals(conn, e2, {"heart_rate_bpm": 96}, verified=False, source="device")
        _symptoms(conn, e2, ["cough"], SCREEN)

        # 3. Conflicting temperature readings and conflicting allergy documentation.
        p3 = repo.create_patient(conn, "Neema", "Mfano", "female", 1999, "USR-intake", patient_id="SYN-P-0003")
        repo.upsert_record_source(conn, p3, "electronic_record", "available", None)
        repo.upsert_record_source(conn, p3, "paper_record", "available", None)
        h3 = repo.create_encounter(conn, p3, fac, "fever", "Fever and body aches", "USR-intake",
                                   arrived_at=_ago(days=200), status="closed", encounter_id="SYN-E-0003-H1",
                                   record_source="paper_record_transcribed")
        repo.add_note(conn, h3, "allergy", "Penicillin allergy (rash)", "paper_record_transcribed",
                      source_ref="Paper file p.1", recorded_by="historic", recorded_at=_ago(days=200))
        repo.add_note(conn, h3, "allergy", "No known drug allergies", "electronic_record",
                      source_ref="EMR allergy list", recorded_by="historic", recorded_at=_ago(days=60))
        e3 = repo.create_encounter(conn, p3, fac, "fever", "Feeling hot since last night", "USR-intake",
                                   arrived_at=_ago(minutes=12), encounter_id="SYN-E-0003")
        _vitals(conn, e3, {k: v for k, v in NORMALISH.items() if k != "temperature_c"})
        _vitals(conn, e3, {"temperature_c": 38.1})
        _vitals(conn, e3, {"temperature_c": 39.4}, source="device", by="USR-nurse2")
        _symptoms(conn, e3, ["fever"], SCREEN)

        # 4. Escalation placeholder criterion met (SpO2 below demo threshold) while temperature is missing.
        p4 = repo.create_patient(conn, "Juma", "Mfano", "male", 1962, "USR-intake", patient_id="SYN-P-0004")
        repo.upsert_record_source(conn, p4, "electronic_record", "available", None)
        e4 = repo.create_encounter(conn, p4, fac, "chest_pain", "Tight chest and short of breath", "USR-intake",
                                   arrived_at=_ago(minutes=6), encounter_id="SYN-E-0004")
        _vitals(conn, e4, {"heart_rate_bpm": 118, "resp_rate_bpm": 28, "spo2_pct": 88, "avpu": "A"})
        _symptoms(conn, e4, ["chest_pain", "difficulty_breathing"], ["convulsion"])

        # 5. New patient: no previous encounters and the paper file could not be located.
        p5 = repo.create_patient(conn, "Rehema", "Mfano", "female", 2004, "USR-intake", patient_id="SYN-P-0005")
        repo.upsert_record_source(conn, p5, "paper_record", "not_located", "Paper file requested from records room")
        repo.create_encounter(conn, p5, fac, "abdominal_pain", "Lower abdominal pain since morning", "USR-intake",
                              arrived_at=_ago(minutes=3), encounter_id="SYN-E-0005")

        for enc in ("SYN-E-0001", "SYN-E-0002", "SYN-E-0003", "SYN-E-0004", "SYN-E-0005"):
            repo.ensure_queue_entry(conn, enc)
        audit.record(conn, "synthetic_data_seeded", outcome="success", actor_type="system",
                     details={"patients": 5, "users": len(DEMO_USERS)})
    return {"users": len(DEMO_USERS), "patients": 5}
