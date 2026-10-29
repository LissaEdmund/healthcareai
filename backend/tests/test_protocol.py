"""Deterministic protocol evaluation (FR-008..FR-011; EV-03, EV-05, EV-06)."""

from pathlib import Path

import pytest
import yaml

from hospitalcare import config
from hospitalcare import repositories as repo
from hospitalcare.services import protocol as ps

DEMO = ("SYNTHETIC-DEMO-OPD", "0.1.0")


def _evaluate(conn, encounter_id, protocol=DEMO, directory=None):
    return ps.evaluate(*protocol, repo.observations_for_encounters(conn, [encounter_id]),
                       repo.symptoms_for_encounter(conn, encounter_id), directory=directory)


def _write_protocol(directory: Path, **changes) -> tuple[str, str]:
    data = yaml.safe_load((directory / "SYNTHETIC-DEMO-OPD_v0.1.0.yaml").read_text(encoding="utf-8"))
    data.update(changes)
    path = directory / f"{data['protocol_id']}_v{data['version']}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return data["protocol_id"], data["version"]


def test_complete_evidence_produces_traceable_proposal(conn):
    r = _evaluate(conn, "SYN-E-0001")
    assert r["status"] == "PROPOSED" and r["proposed_priority"] == "DEMO-P3"
    assert r["protocol_status"] == "synthetic_demo" and r["is_clinical_protocol"] is False
    assert len(r["protocol_sha256"]) == 64
    [rule] = r["matched_rules"]
    assert rule["rule_id"] == "DEFAULT"
    for c in rule["criteria_met"]:
        ev = c["evidence"]
        assert ev["recorded_at"] and ev["source_type"]
        assert ev.get("observation_id", "").startswith("OBS-") or ev.get("symptom_id", "").startswith("SYM-")
    assert r["review_required"] and r["historical_context_used"] is False


def test_deterministic(conn):
    a, b = _evaluate(conn, "SYN-E-0001"), _evaluate(conn, "SYN-E-0001")
    a.pop("evaluated_at"), b.pop("evaluated_at")
    assert a == b


def test_ev06_missing_and_unverified_evidence_is_insufficient(conn):
    r = _evaluate(conn, "SYN-E-0002")
    assert r["status"] == "INSUFFICIENT_EVIDENCE" and r["proposed_priority"] is None
    missing = {m["field"]: m["reason"] for m in r["missing_information"]}
    assert missing["spo2_pct"] == "not recorded for this encounter"
    assert missing["heart_rate_bpm"] == "recorded but not verified"
    assert "spo2_pct" not in r["evidence_used"]


def test_ev03_conflicting_evidence_blocks_priority(conn):
    r = _evaluate(conn, "SYN-E-0003")
    assert r["status"] == "CONFLICTING_EVIDENCE" and r["proposed_priority"] is None
    assert r["conflicts"][0]["field"] == "temperature_c"
    assert {v["value"] for v in r["conflicts"][0]["values"]} == {38.1, 39.4}


def test_conflict_resolved_by_superseding(conn, nurse):
    _, p = nurse
    obs = [o for o in repo.observations_for_encounters(conn, ["SYN-E-0003"]) if o["code"] == "temperature_c"]
    wrong = next(o for o in obs if o["value_num"] == 38.1)
    repo.set_observation_status(conn, wrong["id"], "superseded", p.user_id, "re-measured")
    r = _evaluate(conn, "SYN-E-0003")
    assert r["status"] == "PROPOSED" and r["proposed_priority"] == "DEMO-P2"
    assert any(c["field"] == "temperature_c" for c in r["matched_rules"][0]["criteria_met"])


def test_escalation_flag_raised_even_when_unresolved(conn):
    r = _evaluate(conn, "SYN-E-0004")
    assert r["status"] == "INSUFFICIENT_EVIDENCE" and r["proposed_priority"] is None
    assert r["urgent_flag"] is True and "immediate clinical review" in r["urgent_message"]
    r1 = next(m for m in r["matched_rules"] if m["rule_id"] == "DEMO-R1")
    assert r1["criteria_met"][0]["field"] == "spo2_pct" and r1["criteria_met"][0]["evidence"]["value"] == 88


def test_ev05_missing_protocol_refuses(conn):
    r = _evaluate(conn, "SYN-E-0001", protocol=("NO-SUCH-PROTOCOL", "1.0.0"))
    assert r["status"] == "PROTOCOL_UNAVAILABLE" and r["proposed_priority"] is None and r["matched_rules"] == []


def test_path_like_protocol_ids_rejected(conn):
    r = _evaluate(conn, "SYN-E-0001", protocol=("../../etc/passwd", "1.0.0"))
    assert r["status"] == "PROTOCOL_UNAVAILABLE"


def test_demo_protocol_refused_outside_demo_mode(conn, monkeypatch):
    monkeypatch.setenv("HCAI_DEMO_MODE", "false")
    config.get_settings.cache_clear()
    r = _evaluate(conn, "SYN-E-0001")
    assert r["status"] == "PROTOCOL_NOT_APPROVED" and r["proposed_priority"] is None


def test_draft_protocol_refused(conn, env):
    directory = Path(env["HCAI_REFERENCE_DIR"]) / "protocols"
    pid, ver = _write_protocol(directory, protocol_id="TEST-DRAFT", status="draft")
    r = _evaluate(conn, "SYN-E-0001", protocol=(pid, ver))
    assert r["status"] == "PROTOCOL_NOT_APPROVED"


def test_approved_status_requires_approval_record(env):
    directory = Path(env["HCAI_REFERENCE_DIR"]) / "protocols"
    pid, ver = _write_protocol(directory, protocol_id="TEST-UNSIGNED", status="approved")
    with pytest.raises(ps.ProtocolUnavailable, match="approval"):
        ps.load_protocol(pid, ver)


def test_invalid_rule_reference_rejected(env):
    directory = Path(env["HCAI_REFERENCE_DIR"]) / "protocols"
    data = yaml.safe_load((directory / "SYNTHETIC-DEMO-OPD_v0.1.0.yaml").read_text(encoding="utf-8"))
    data["protocol_id"] = "TEST-BAD"
    data["rules"][0]["criteria"].append({"field": "invented_field", "op": "gt", "value": 1})
    (directory / "TEST-BAD_v0.1.0.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ps.ProtocolUnavailable, match="undeclared field"):
        ps.load_protocol("TEST-BAD", "0.1.0")
    listing = {p.get("file"): p for p in ps.list_protocols()}
    assert listing["TEST-BAD_v0.1.0.yaml"]["valid"] is False


def test_no_default_and_no_match_is_unresolved(conn, env):
    directory = Path(env["HCAI_REFERENCE_DIR"]) / "protocols"
    pid, ver = _write_protocol(directory, protocol_id="TEST-NODEFAULT", default_priority=None)
    r = _evaluate(conn, "SYN-E-0001", protocol=(pid, ver))
    assert r["status"] == "NO_RULE_MATCHED" and r["proposed_priority"] is None


def test_history_never_used_as_evidence(conn):
    # SYN-E-0001-H1 has a historical temperature; the current encounter's value must be the one used.
    r = _evaluate(conn, "SYN-E-0001")
    ev = r["evidence_used"]["temperature_c"]
    current_ids = {o["id"] for o in repo.observations_for_encounters(conn, ["SYN-E-0001"])}
    assert ev["observation_id"] in current_ids


def test_new_encounter_without_observations(conn):
    r = _evaluate(conn, "SYN-E-0005")
    assert r["status"] == "INSUFFICIENT_EVIDENCE"
    assert {m["field"] for m in r["missing_information"]} >= {"temperature_c", "chest_pain"}
    assert all("absence has not been assumed" in m["reason"] for m in r["missing_information"]
               if m["field"] == "chest_pain")
