"""FastAPI application: authenticated HTTP API for the web UI."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import audit
from .. import repositories as repo
from ..agent.graph import RECOVERY
from ..agent.runner import WorkflowRunner, checkpointer_context
from ..catalog import COMPLAINT_CODES, OBSERVATION_CODES, OBSERVATION_SOURCES, SYMPTOM_CODES
from ..config import get_settings
from ..db import DatabaseError, check_health, get_conn, migrate, transaction
from ..llm import model_status
from ..security import (AuthError, PermissionDenied, Principal, authenticate_token, create_session,
                        permissions_for, require, revoke_session, verify_password)
from ..services import context as context_service
from ..services import protocol as protocol_service
from ..services import reviews as review_service

PROTOTYPE_NOTICE = "Prototype using SYNTHETIC data only. Not for clinical use. No real hospital system is connected."


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    problems = settings.validate_for_runtime()
    if problems:
        raise RuntimeError("Configuration error: " + " ".join(problems))
    with get_conn() as conn:
        migrate(conn)
    async with checkpointer_context() as saver:
        app.state.runner = WorkflowRunner(saver)
        yield


app = FastAPI(title="HospitalCare AI API", version="0.1.0", lifespan=lifespan,
              description=PROTOTYPE_NOTICE)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_list, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


# --- Errors -------------------------------------------------------------------------------

def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(AuthError)
async def _auth_error(request: Request, exc: AuthError):
    return _error(401, "UNAUTHENTICATED", str(exc))


@app.exception_handler(PermissionDenied)
async def _permission_error(request: Request, exc: PermissionDenied):
    principal: Principal | None = getattr(request.state, "principal", None)
    with get_conn() as conn:
        audit.record(conn, "access_denied", outcome="denied", principal=principal,
                     details={"method": request.method, "path": request.url.path}, error=str(exc))
    return _error(403, "FORBIDDEN", str(exc))


@app.exception_handler(repo.NotFound)
async def _not_found(request: Request, exc: repo.NotFound):
    return _error(404, "NOT_FOUND", str(exc))


@app.exception_handler(review_service.ReviewError)
@app.exception_handler(repo.Conflict)
async def _conflict(request: Request, exc: Exception):
    return _error(409, "CONFLICT", str(exc))


@app.exception_handler(ValueError)
async def _value_error(request: Request, exc: ValueError):
    return _error(422, "INVALID_REQUEST", str(exc))


@app.exception_handler(DatabaseError)
@app.exception_handler(sqlite3.OperationalError)
async def _db_error(request: Request, exc: Exception):
    return _error(503, "DATABASE_UNAVAILABLE", f"Database unavailable: {exc}")


# --- Dependencies ---------------------------------------------------------------------------

def db() -> Iterator[sqlite3.Connection]:
    with get_conn() as conn:
        yield conn


Conn = Annotated[sqlite3.Connection, Depends(db)]


def current_principal(request: Request, conn: Conn, authorization: Annotated[str | None, Header()] = None) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    principal = authenticate_token(conn, authorization[7:].strip())
    if principal.via != "session":
        raise AuthError("agent delegation tokens are not accepted by the HTTP API")
    request.state.principal = principal
    return principal


User = Annotated[Principal, Depends(current_principal)]


def runner(request: Request) -> WorkflowRunner:
    return request.app.state.runner


# --- Schemas ----------------------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PatientIn(BaseModel):
    given_name: str = Field(min_length=1, max_length=80)
    family_name: str = Field(min_length=1, max_length=80)
    sex: Literal["female", "male", "unknown"]
    birth_year: int | None = Field(default=None, ge=1900, le=2100)


class EncounterIn(BaseModel):
    patient_id: str = Field(pattern=r"^SYN-P-[A-Z0-9-]+$")
    complaint_code: str
    chief_complaint: str = Field(min_length=2, max_length=500)
    complaint_source: Literal["patient_reported", "electronic_record", "paper_record_transcribed"] = "patient_reported"
    record_source: Literal["electronic_record", "paper_record_transcribed"] = "electronic_record"


class ObservationIn(BaseModel):
    code: str
    value: float | str
    source_type: Literal["clinician_measured", "device", "patient_reported", "paper_record_transcribed"]
    verification_status: Literal["verified", "unverified"] = "unverified"
    source_ref: str | None = Field(default=None, max_length=200)


class SymptomIn(BaseModel):
    code: str
    present: bool
    source_type: Literal["patient_reported", "clinician_observed"] = "patient_reported"


class ObservationStatusIn(BaseModel):
    status: Literal["superseded", "entered_in_error"]
    reason: str = Field(min_length=3, max_length=500)


class WorkflowIn(BaseModel):
    encounter_id: str
    protocol_id: str = "SYNTHETIC-DEMO-OPD"
    protocol_version: str = "0.1.0"


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "request_clarification", "override"]
    rationale: str = Field(min_length=3, max_length=1000)
    override_priority: str | None = None


# --- Health, auth, meta ------------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    from ..mcp_clients import ReadOnlyFilesystemClient

    db_ok, db_detail = check_health()
    entry = get_settings().filesystem_mcp_entry_path
    model = model_status()
    return {"status": "ok" if db_ok else "degraded", "notice": PROTOTYPE_NOTICE,
            "database": {"ok": db_ok, "detail": db_detail}, "model": model,
            "filesystem_mcp": {"installed": entry.is_file(), "root": str(ReadOnlyFilesystemClient().root.name)},
            "demo_mode": get_settings().demo_mode, "facility_code": get_settings().facility_code}


@app.post("/api/auth/login")
def login(body: LoginIn, conn: Conn) -> dict[str, Any]:
    user = repo.get_user_by_username(conn, body.username)
    if user is None or not user["active"] or not verify_password(body.password, user["password_hash"]):
        audit.record(conn, "login_failed", outcome="denied", actor_type="user",
                     details={"username": body.username[:64]})
        raise AuthError("invalid username or password")
    token = create_session(conn, user["id"])
    audit.record(conn, "login", outcome="success", actor_type="user", actor_id=user["id"])
    return {"token": token, "user": _user_out(user["id"], user["username"], user["display_name"], user["role"])}


def _user_out(user_id: str, username: str, display_name: str, role: str) -> dict[str, Any]:
    return {"id": user_id, "username": username, "display_name": display_name, "role": role,
            "permissions": sorted(permissions_for(role))}


@app.post("/api/auth/logout")
def logout(user: User, conn: Conn, authorization: Annotated[str, Header()]) -> dict[str, str]:
    revoke_session(conn, authorization[7:].strip())
    audit.record(conn, "logout", outcome="success", principal=user)
    return {"status": "logged_out"}


@app.get("/api/auth/me")
def me(user: User) -> dict[str, Any]:
    return _user_out(user.user_id, user.username, user.display_name, user.role)


@app.get("/api/catalog")
def catalog(user: User) -> dict[str, Any]:
    return {"observation_codes": {k: {**v, "range": v.get("range")} for k, v in OBSERVATION_CODES.items()},
            "observation_sources": OBSERVATION_SOURCES, "symptom_codes": SYMPTOM_CODES,
            "complaint_codes": COMPLAINT_CODES}


@app.get("/api/dashboard")
def dashboard(user: User, conn: Conn) -> dict[str, Any]:
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    data: dict[str, Any] = {"notice": PROTOTYPE_NOTICE, "model": model_status(),
                            "demo_mode": get_settings().demo_mode}
    if user.can("patient:read_basic"):
        data["encounters"] = {"open": count("SELECT COUNT(*) FROM encounters WHERE status='open'"),
                              "total": count("SELECT COUNT(*) FROM encounters")}
    if user.can("review:read"):
        data["reviews"] = {s: count(f"SELECT COUNT(*) FROM review_requests WHERE status='{s}'")
                           for s in ("PENDING", "APPROVED", "REJECTED", "CLARIFICATION_REQUESTED", "EXECUTED",
                                     "EXECUTION_FAILED")}
        data["urgent_pending"] = count(
            "SELECT COUNT(*) FROM review_requests r JOIN protocol_evaluations e ON e.id = r.evaluation_id "
            "WHERE r.status='PENDING' AND e.urgent_flag=1")
    if user.can("audit:read") or user.can("triage:run"):
        events = audit.list_events(conn, limit=10)
        data["recent_events"] = [{k: e[k] for k in ("ts", "event_type", "actor_id", "tool_name", "outcome",
                                                   "encounter_id", "review_id")} for e in events]
    return data


# --- Patients, encounters, observations --------------------------------------------------------------

@app.get("/api/patients")
def patients(user: User, conn: Conn, q: str | None = Query(default=None, max_length=80)) -> list[dict]:
    require(user, "patient:read_basic")
    return repo.search_patients(conn, q)


@app.post("/api/patients", status_code=201)
def create_patient(body: PatientIn, user: User, conn: Conn) -> dict:
    require(user, "patient:create")
    with transaction(conn):
        pid = repo.create_patient(conn, body.given_name, body.family_name, body.sex, body.birth_year, user.user_id)
        audit.record(conn, "patient_created", outcome="success", principal=user, details={"patient_id": pid})
    return repo.get_patient(conn, pid)


@app.get("/api/patients/{patient_id}/context")
def patient_context(patient_id: str, encounter_id: str, user: User, conn: Conn) -> dict:
    require(user, "patient:read_basic")
    ctx = context_service.build_patient_context(conn, user, patient_id, encounter_id)
    audit.record(conn, "patient_context_viewed", outcome="success", principal=user, encounter_id=encounter_id,
                 output_payload=ctx, details={"categories_returned": ctx["categories_returned"]})
    return ctx


@app.get("/api/encounters")
def encounters(user: User, conn: Conn, status: Literal["open", "closed"] | None = "open",
               patient_id: str | None = None) -> list[dict]:
    require(user, "patient:read_basic")
    return repo.list_encounters(conn, status=status, patient_id=patient_id)


@app.post("/api/encounters", status_code=201)
def create_encounter(body: EncounterIn, user: User, conn: Conn) -> dict:
    require(user, "encounter:create")
    if body.complaint_code not in COMPLAINT_CODES:
        raise ValueError(f"unknown complaint_code '{body.complaint_code}'")
    with transaction(conn):
        eid = repo.create_encounter(conn, body.patient_id, get_settings().facility_code, body.complaint_code,
                                    body.chief_complaint, user.user_id, complaint_source=body.complaint_source,
                                    record_source=body.record_source)
        repo.ensure_queue_entry(conn, eid)
        audit.record(conn, "encounter_created", outcome="success", principal=user, encounter_id=eid,
                     input_payload=body.model_dump())
    return repo.get_encounter(conn, eid)


@app.get("/api/encounters/{encounter_id}")
def encounter_detail(encounter_id: str, user: User, conn: Conn) -> dict:
    require(user, "patient:read_basic")
    enc = repo.get_encounter(conn, encounter_id)
    enc["patient"] = repo.get_patient(conn, enc["patient_id"])
    if user.can("patient:read_history"):
        enc["observations"] = repo.observations_for_encounters(conn, [encounter_id])
        enc["symptoms"] = repo.symptoms_for_encounter(conn, encounter_id)
        enc["conflicts"] = context_service.find_observation_conflicts(enc["observations"])
    enc["synthetic_queue"] = repo.get_queue_entry(conn, encounter_id)
    enc["workflows"] = repo.list_workflow_runs(conn, encounter_id) if user.can("triage:run") else []
    return enc


def _validate_observation(body: ObservationIn) -> tuple[float | None, str | None, str | None]:
    meta = OBSERVATION_CODES.get(body.code)
    if meta is None:
        raise ValueError(f"unknown observation code '{body.code}'")
    if meta["type"] == "number":
        try:
            value = float(body.value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{meta['label']} must be a number") from exc
        low, high = meta["range"]
        if not low <= value <= high:
            raise ValueError(f"{meta['label']} {value} is outside the data-entry range {low}–{high} {meta['unit']}; "
                             "check for a typing error")
        return value, None, meta["unit"]
    value = str(body.value).strip().upper()
    if value not in meta["values"]:
        raise ValueError(f"{meta['label']} must be one of {', '.join(meta['values'])}")
    return None, value, meta["unit"]


@app.post("/api/encounters/{encounter_id}/observations", status_code=201)
def add_observation(encounter_id: str, body: ObservationIn, user: User, conn: Conn) -> dict:
    require(user, "observation:record")
    num, txt, unit = _validate_observation(body)
    enc = repo.get_encounter(conn, encounter_id)
    if enc["status"] != "open":
        raise repo.Conflict("encounter is closed")
    if body.verification_status == "verified" and not user.can("observation:verify"):
        raise PermissionDenied("recording a verified observation requires observation:verify")
    with transaction(conn):
        oid = repo.add_observation(conn, encounter_id, body.code, value_num=num, value_text=txt, unit=unit,
                                   source_type=body.source_type, verification_status=body.verification_status,
                                   recorded_by=user.user_id, source_ref=body.source_ref)
        audit.record(conn, "observation_recorded", outcome="success", principal=user, encounter_id=encounter_id,
                     input_payload=body.model_dump(), details={"observation_id": oid, "code": body.code,
                                                               "verification_status": body.verification_status})
    return repo.get_observation(conn, oid)


@app.post("/api/encounters/{encounter_id}/symptoms", status_code=201)
def add_symptom(encounter_id: str, body: SymptomIn, user: User, conn: Conn) -> dict:
    require(user, "symptom:record")
    if body.code not in SYMPTOM_CODES:
        raise ValueError(f"unknown symptom code '{body.code}'")
    repo.get_encounter(conn, encounter_id)
    with transaction(conn):
        sid = repo.add_symptom(conn, encounter_id, body.code, body.present, body.source_type, user.user_id)
        audit.record(conn, "symptom_recorded", outcome="success", principal=user, encounter_id=encounter_id,
                     details={"symptom_id": sid, "code": body.code, "present": body.present})
    return {"id": sid, "code": body.code, "present": body.present}


@app.post("/api/observations/{observation_id}/verify")
def verify_observation(observation_id: str, user: User, conn: Conn) -> dict:
    require(user, "observation:verify")
    with transaction(conn):
        repo.verify_observation(conn, observation_id, user.user_id)
        obs = repo.get_observation(conn, observation_id)
        audit.record(conn, "observation_verified", outcome="success", principal=user,
                     encounter_id=obs["encounter_id"], details={"observation_id": observation_id})
    return obs


@app.post("/api/observations/{observation_id}/status")
def observation_status(observation_id: str, body: ObservationStatusIn, user: User, conn: Conn) -> dict:
    require(user, "observation:verify")
    with transaction(conn):
        repo.set_observation_status(conn, observation_id, body.status, user.user_id, body.reason)
        obs = repo.get_observation(conn, observation_id)
        audit.record(conn, "observation_status_changed", outcome="success", principal=user,
                     encounter_id=obs["encounter_id"], details={"observation_id": observation_id,
                                                                "status": body.status, "reason": body.reason})
    return obs


# --- Protocols and workflows -------------------------------------------------------------------------

@app.get("/api/protocols")
def protocols(user: User) -> list[dict]:
    require(user, "triage:run")
    return protocol_service.list_protocols()


@app.post("/api/workflows", status_code=202)
async def start_workflow(body: WorkflowIn, request: Request, user: User) -> dict:
    thread_id = runner(request).start(user, body.encounter_id, body.protocol_id, body.protocol_version)
    return {"thread_id": thread_id, "status": "RUNNING"}


@app.get("/api/workflows")
def workflows(user: User, conn: Conn, encounter_id: str | None = None) -> list[dict]:
    require(user, "triage:run")
    return repo.list_workflow_runs(conn, encounter_id)


@app.get("/api/workflows/{thread_id}")
async def workflow_detail(thread_id: str, request: Request, user: User) -> dict:
    require(user, "triage:run")
    data = await runner(request).state(thread_id)
    data["recovery"] = data["state"].get("recovery") or RECOVERY.get(data["run"]["status"])
    return data


# --- Reviews and queue -----------------------------------------------------------------------------------

@app.get("/api/reviews")
def reviews(user: User, conn: Conn, status: str | None = None) -> list[dict]:
    require(user, "review:read")
    return repo.list_reviews(conn, status)


@app.get("/api/reviews/{review_id}")
def review_detail(review_id: str, user: User, conn: Conn) -> dict:
    require(user, "review:read")
    review = repo.get_review(conn, review_id)
    review["evaluation"] = repo.get_evaluation(conn, review["evaluation_id"])
    review["action"] = repo.get_action_for_review(conn, review_id)
    review["encounter"] = repo.get_encounter(conn, review["encounter_id"])
    review["patient"] = repo.get_patient(conn, review["encounter"]["patient_id"])
    review["queue_entry"] = repo.get_queue_entry(conn, review["encounter_id"])
    try:
        levels = protocol_service.load_protocol(review["evaluation"]["protocol_id"],
                                                review["evaluation"]["protocol_version"]).protocol.priority_levels
        review["priority_levels"] = [lvl.model_dump() for lvl in levels]
    except protocol_service.ProtocolError:
        review["priority_levels"] = []
    return review


@app.post("/api/reviews/{review_id}/decision")
async def decide(review_id: str, body: DecisionIn, request: Request, user: User, conn: Conn) -> dict:
    review = review_service.record_decision(conn, user, review_id, body.decision, body.rationale,
                                            body.override_priority)
    resumed = None
    run = repo.find_workflow_by_review(conn, review_id)
    if run is not None:
        runner(request).resume(user, run["thread_id"])
        resumed = run["thread_id"]
    return {"review": review, "workflow_resumed": resumed,
            "queue_effect": "An approved action is applied by the workflow and then verified."
            if review["status"] == "APPROVED" else "No queue change."}


@app.post("/api/reviews/{review_id}/execute")
def execute(review_id: str, user: User, conn: Conn) -> dict:
    """Recovery path: retry an approved action whose execution failed or whose workflow is unavailable."""
    return review_service.execute_approved_action(conn, user, review_id)


@app.get("/api/queue")
def queue(user: User, conn: Conn) -> dict:
    require(user, "queue:read")
    return {"label": "SYNTHETIC QUEUE — not connected to any hospital system", "entries": repo.list_queue(conn)}


# --- Audit ------------------------------------------------------------------------------------------------

@app.get("/api/audit")
def audit_log(user: User, conn: Conn, limit: int = Query(default=200, ge=1, le=1000), event_type: str | None = None,
              encounter_id: str | None = None, review_id: str | None = None,
              workflow_thread_id: str | None = None) -> list[dict]:
    require(user, "audit:read")
    return audit.list_events(conn, limit=limit, event_type=event_type, encounter_id=encounter_id,
                             review_id=review_id, workflow_thread_id=workflow_thread_id)


@app.get("/api/audit/verify")
def audit_verify(user: User, conn: Conn) -> dict:
    require(user, "audit:read")
    return audit.verify_chain(conn)
