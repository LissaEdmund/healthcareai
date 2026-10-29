"""Starts, resumes and inspects triage workflow runs (D-012: runs execute as background tasks)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from .. import audit
from .. import repositories as repo
from ..config import get_settings
from ..db import get_conn
from ..security import Principal, issue_delegation_token, require
from .graph import TOKEN_VAULT, build_graph

START_SCOPES = {"context:read", "triage:evaluate", "review:create", "review:read"}
RESUME_SCOPES = {"review:read", "review:execute"}


class WorkflowRunner:
    def __init__(self, checkpointer: AsyncSqliteSaver):
        self.graph = build_graph(checkpointer)
        self.tasks: dict[str, asyncio.Task] = {}

    def _config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    async def _run(self, thread_id: str, payload: Any) -> None:
        try:
            await self.graph.ainvoke(payload, self._config(thread_id))
        except Exception as exc:  # never leave a run silently "RUNNING"
            with get_conn() as conn:
                repo.update_workflow_run(conn, thread_id, status="ERROR", last_error=f"{exc.__class__.__name__}: {exc}")
                audit.record(conn, "workflow_error", outcome="failure", actor_type="agent",
                             workflow_thread_id=thread_id, error=f"{exc.__class__.__name__}: {exc}")
            TOKEN_VAULT.pop(thread_id, None)

    def start(self, principal: Principal, encounter_id: str, protocol_id: str, protocol_version: str) -> str:
        require(principal, "triage:run")
        thread_id = f"WF-{uuid.uuid4().hex[:12]}"
        with get_conn() as conn:
            repo.get_encounter(conn, encounter_id)
            repo.create_workflow_run(conn, thread_id, encounter_id, protocol_id, protocol_version, principal.user_id)
            audit.record(conn, "workflow_requested", outcome="success", principal=principal,
                         encounter_id=encounter_id, workflow_thread_id=thread_id,
                         details={"protocol_id": protocol_id, "protocol_version": protocol_version})
        TOKEN_VAULT[thread_id] = issue_delegation_token(principal, encounter_id, START_SCOPES)
        state = {"thread_id": thread_id, "encounter_id": encounter_id, "protocol_id": protocol_id,
                 "protocol_version": protocol_version, "started_by": principal.user_id, "status": "RUNNING",
                 "errors": [], "steps": []}
        self.tasks[thread_id] = asyncio.create_task(self._run(thread_id, state))
        return thread_id

    def resume(self, principal: Principal, thread_id: str) -> None:
        """Resume a paused run after a decision was recorded. The decision itself is read from the DB."""
        with get_conn() as conn:
            run = repo.get_workflow_run(conn, thread_id)
            repo.update_workflow_run(conn, thread_id, status="RUNNING", current_step="await_decision")
        TOKEN_VAULT[thread_id] = issue_delegation_token(principal, run["encounter_id"], RESUME_SCOPES)
        self.tasks[thread_id] = asyncio.create_task(
            self._run(thread_id, Command(resume={"resumed_by": principal.user_id})))

    async def wait(self, thread_id: str, timeout: float = 600) -> None:
        task = self.tasks.get(thread_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), timeout)

    async def state(self, thread_id: str) -> dict[str, Any]:
        with get_conn() as conn:
            run = repo.get_workflow_run(conn, thread_id)
        snapshot = await self.graph.aget_state(self._config(thread_id))
        values = dict(snapshot.values or {})
        doc = values.get("protocol_document")
        if doc and "text" in doc:
            values["protocol_document"] = {k: v for k, v in doc.items() if k != "text"}
        return {"run": run, "state": values, "next": list(snapshot.next or []),
                "paused_for_review": "await_decision" in (snapshot.next or ())}


def checkpointer_context():
    path = get_settings().checkpoint_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(str(path))
