"""HTTP API: authentication, authorization, validation and a full approval flow over HTTP (EV-07, EV-08, EV-15)."""

import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_PASSWORD


@pytest.fixture
def client(conn):
    from hospitalcare.api.app import app

    with TestClient(app) as c:
        yield c


def login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_is_public_and_contains_no_patient_data(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"]["ok"]
    assert "SYN-P" not in r.text and "Mfano" not in r.text


def test_login_failure_and_missing_token(client, conn):
    r = client.post("/api/auth/login", json={"username": "nurse.demo", "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["message"] == "invalid username or password"
    assert client.get("/api/patients").status_code == 401
    row = conn.execute("SELECT details_json FROM audit_events WHERE event_type='login_failed'").fetchone()
    assert "wrong" not in row[0], "passwords are never logged"


def test_logout_revokes_token(client):
    h = login(client, "nurse.demo")
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_delegation_token_rejected_by_http_api(client, conn, nurse):
    from hospitalcare.security import issue_delegation_token

    token = issue_delegation_token(nurse[1], "SYN-E-0001", {"context:read"})
    r = client.get("/api/patients", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


@pytest.mark.parametrize("username, path", [
    ("auditor.demo", "/api/patients"),
    ("auditor.demo", "/api/reviews"),
    ("admin.demo", "/api/patients/SYN-P-0001/context?encounter_id=SYN-E-0001"),
    ("intake.demo", "/api/reviews"),
    ("intake.demo", "/api/audit"),
    ("nurse.demo", "/api/audit"),
])
def test_ev15_role_restrictions(client, conn, username, path):
    r = client.get(path, headers=login(client, username))
    assert r.status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_type='access_denied'").fetchone()[0] >= 1


def test_intake_clerk_cannot_record_vitals_or_start_triage(client):
    h = login(client, "intake.demo")
    r = client.post("/api/encounters/SYN-E-0005/observations", headers=h,
                    json={"code": "temperature_c", "value": 37, "source_type": "clinician_measured"})
    assert r.status_code == 403
    assert client.post("/api/workflows", headers=h, json={"encounter_id": "SYN-E-0005"}).status_code == 403


def test_observation_validation(client):
    h = login(client, "nurse.demo")
    url = "/api/encounters/SYN-E-0005/observations"
    bad = [{"code": "temperature_c", "value": 370, "source_type": "device"},
           {"code": "invented", "value": 1, "source_type": "device"},
           {"code": "avpu", "value": "Z", "source_type": "clinician_measured"},
           {"code": "spo2_pct", "value": "high", "source_type": "device"}]
    for body in bad:
        assert client.post(url, headers=h, json=body).status_code == 422, body
    ok = client.post(url, headers=h, json={"code": "temperature_c", "value": 37.4, "source_type": "device",
                                           "verification_status": "verified"})
    assert ok.status_code == 201 and ok.json()["verified_by"] == "USR-nurse1"


def test_patient_ids_are_synthetic(client):
    h = login(client, "intake.demo")
    r = client.post("/api/patients", headers=h, json={"given_name": "Test", "family_name": "Mfano", "sex": "male"})
    assert r.status_code == 201 and r.json()["id"].startswith("SYN-P-") and r.json()["is_synthetic"] == 1


def _wait_for(client, h, thread_id, predicate, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/workflows/{thread_id}", headers=h).json()
        if predicate(data):
            return data
        time.sleep(0.3)
    raise AssertionError(f"workflow did not reach expected state: {data['run']}")


def test_ev08_full_flow_over_http(client):
    nurse = login(client, "nurse.demo")
    reviewer = login(client, "nurse2.demo")
    r = client.post("/api/workflows", headers=nurse, json={"encounter_id": "SYN-E-0001"})
    assert r.status_code == 202
    tid = r.json()["thread_id"]
    data = _wait_for(client, nurse, tid, lambda d: d["paused_for_review"])
    review_id = data["state"]["review_id"]

    queue = client.get("/api/queue", headers=nurse).json()
    assert "SYNTHETIC" in queue["label"]
    assert next(e for e in queue["entries"] if e["encounter_id"] == "SYN-E-0001")["priority"] is None

    # EV-07: executing before approval is refused server-side
    assert client.post(f"/api/reviews/{review_id}/execute", headers=reviewer).status_code == 409
    # Auditor cannot decide
    assert client.post(f"/api/reviews/{review_id}/decision", headers=login(client, "auditor.demo"),
                       json={"decision": "approve", "rationale": "nope"}).status_code == 403
    # Missing rationale rejected
    assert client.post(f"/api/reviews/{review_id}/decision", headers=reviewer,
                       json={"decision": "approve", "rationale": ""}).status_code == 422

    r = client.post(f"/api/reviews/{review_id}/decision", headers=reviewer,
                    json={"decision": "approve", "rationale": "Verified against chart"})
    assert r.status_code == 200 and r.json()["workflow_resumed"] == tid
    data = _wait_for(client, nurse, tid, lambda d: d["run"]["status"] not in ("RUNNING", "AWAITING_REVIEW"))
    assert data["run"]["status"] == "COMPLETED"
    entry = next(e for e in client.get("/api/queue", headers=nurse).json()["entries"]
                 if e["encounter_id"] == "SYN-E-0001")
    assert entry["priority"] == "DEMO-P3"

    # EV-10 over HTTP: second decision and second execution do not apply anything twice
    assert client.post(f"/api/reviews/{review_id}/decision", headers=reviewer,
                       json={"decision": "approve", "rationale": "again"}).status_code == 409
    again = client.post(f"/api/reviews/{review_id}/execute", headers=reviewer)
    assert again.status_code == 200 and again.json()["duplicate"] is True

    auditor = login(client, "auditor.demo")
    events = client.get(f"/api/audit?workflow_thread_id={tid}", headers=auditor).json()
    assert {e["event_type"] for e in events} >= {"workflow_requested", "review_decided", "workflow_finished"}
    assert client.get("/api/audit/verify", headers=auditor).json()["valid"] is True
