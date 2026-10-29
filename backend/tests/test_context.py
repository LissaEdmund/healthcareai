"""Patient context retrieval: provenance, missing data, conflicts, recurrence, authorization (EV-01..04, EV-15)."""

from hospitalcare.services.context import RECURRENCE_STATEMENT, build_patient_context


def test_ev01_complete_encounter_is_cited(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001")
    assert ctx["data_label"].startswith("SYNTHETIC")
    assert ctx["patient"]["is_synthetic"] is True
    assert {o["code"] for o in ctx["current_observations"]} >= {"temperature_c", "spo2_pct", "avpu"}
    for o in ctx["current_observations"]:
        assert o["id"].startswith("OBS-") and o["recorded_at"] and o["source_type"] and o["recorded_by"]
    assert len(ctx["previous_encounters"]) == 2
    for enc in ctx["previous_encounters"]:
        for note in enc["notes"]:
            assert note["source_type"] and note["recorded_at"] and note["id"].startswith("NOTE-")
    assert ctx["conflicts"] == []
    # Patient-reported vs clinically recorded is explicit
    assert ctx["encounter"]["complaint_provenance"] == "patient_reported"
    assert all(s["provenance"] == "patient_reported" for s in ctx["current_symptoms"])
    assert all(o["provenance"] == "clinically_recorded" for o in ctx["current_observations"])


def test_ev02_missing_vital_reported_not_invented(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0002", "SYN-E-0002")
    assert "spo2_pct" not in {o["code"] for o in ctx["current_observations"]}
    items = " ".join(m["item"] for m in ctx["missing_information"])
    assert "Oxygen saturation" in items
    assert "verification: Heart rate" in items  # unverified, not silently accepted


def test_ev03_conflicts_surface_with_sources(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0003", "SYN-E-0003")
    fields = {c["field"]: c for c in ctx["conflicts"]}
    assert set(fields) == {"temperature_c", "allergy"}
    temps = {v["value"] for v in fields["temperature_c"]["values"]}
    assert temps == {38.1, 39.4}
    assert {v["source_type"] for v in fields["temperature_c"]["values"]} == {"clinician_measured", "device"}
    assert "verify" in fields["temperature_c"]["message"]
    assert {v["source_type"] for v in fields["allergy"]["values"]} == {"paper_record_transcribed",
                                                                         "electronic_record"}


def test_ev04_recurring_complaint_without_failure_claim(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001")
    rec = ctx["recurring_complaint"]
    assert rec["detected"] and set(rec["prior_encounter_ids"]) == {"SYN-E-0001-H1", "SYN-E-0001-H2"}
    assert rec["statement"] == RECURRENCE_STATEMENT
    assert "does not by itself indicate that previous treatment failed" in rec["statement"]
    outcomes = [n["content"] for e in ctx["previous_encounters"] for n in e["notes"] if n["category"] == "outcome"]
    assert outcomes, "documented outcomes are shown"


def test_missing_records_not_treated_as_absence(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0005", "SYN-E-0005")
    details = " ".join(m["detail"] for m in ctx["missing_information"])
    assert "does not mean it did not happen" in details
    assert ctx["recurring_complaint"]["detected"] is False


def test_ev15_intake_clerk_cannot_read_history(conn, intake):
    _, p = intake
    ctx = build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001")
    assert "history" in ctx["categories_withheld"]
    assert "previous_encounters" not in ctx
    assert "current_observations" not in ctx
    assert ctx["encounter"]["chief_complaint"]  # basic intake info still visible


def test_encounter_patient_mismatch_rejected(conn, nurse):
    import pytest

    _, p = nurse
    with pytest.raises(ValueError):
        build_patient_context(conn, p, "SYN-P-0002", "SYN-E-0001")
