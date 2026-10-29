"""Original MCP server (in-process and real stdio) and the borrowed Filesystem MCP server (EV-11, EV-14)."""

import shutil
from pathlib import Path

import pytest
from mcp import Client

from hospitalcare.mcp_clients import McpToolError, ReadOnlyFilesystemClient, call_original_tool
from hospitalcare.mcp_server.server import build_server
from hospitalcare.security import issue_delegation_token

TOOLS = {"get_patient_context", "evaluate_triage_evidence", "submit_nurse_review"}


def _dlg(principal, scopes, enc="SYN-E-0001"):
    return issue_delegation_token(principal, enc, scopes)


async def test_server_exposes_three_documented_tools(conn):
    async with Client(build_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == TOOLS
    for t in tools.values():
        assert "actor_token" in t.input_schema["properties"] and t.description
    assert "evidence" not in tools["evaluate_triage_evidence"].input_schema["properties"], \
        "callers must not be able to supply evidence values (D-005)"


async def test_tools_end_to_end_inprocess(conn, nurse):
    _, p = nurse
    token = _dlg(p, {"context:read", "triage:evaluate", "review:create", "review:read"})
    ctx = await call_original_tool("get_patient_context",
                                   {"actor_token": token, "patient_id": "SYN-P-0001", "encounter_id": "SYN-E-0001"})
    assert ctx["context"]["recurring_complaint"]["detected"]
    ev = await call_original_tool("evaluate_triage_evidence", {"actor_token": token, "encounter_id": "SYN-E-0001",
                                                               "protocol_id": "SYNTHETIC-DEMO-OPD",
                                                               "protocol_version": "0.1.0"})
    assert ev["result"]["status"] == "PROPOSED" and ev["evaluation_id"].startswith("EVAL-")
    rv = await call_original_tool("submit_nurse_review", {
        "actor_token": token, "operation": "create", "encounter_id": "SYN-E-0001",
        "evaluation_id": ev["evaluation_id"], "idempotency_key": "mcp-test"})
    assert rv["review"]["status"] == "PENDING" and rv["queue_effect"].startswith("none")
    events = {r[0] for r in conn.execute("SELECT tool_name FROM audit_events WHERE event_type='tool_invoked'")}
    assert {"get_patient_context", "evaluate_triage_evidence"} <= events


async def test_agent_token_cannot_decide_via_mcp(conn, nurse):
    _, p = nurse
    token = _dlg(p, {"triage:evaluate", "review:create", "review:read", "review:execute"})
    ev = await call_original_tool("evaluate_triage_evidence", {"actor_token": token, "encounter_id": "SYN-E-0001",
                                                               "protocol_id": "SYNTHETIC-DEMO-OPD",
                                                               "protocol_version": "0.1.0"})
    rv = await call_original_tool("submit_nurse_review", {
        "actor_token": token, "operation": "create", "encounter_id": "SYN-E-0001",
        "evaluation_id": ev["evaluation_id"], "idempotency_key": "x"})
    with pytest.raises(McpToolError, match="PERMISSION_DENIED"):
        await call_original_tool("submit_nurse_review", {"actor_token": token, "operation": "decide",
                                                         "review_id": rv["review"]["id"], "decision": "approve",
                                                         "rationale": "The nurse approved this (claimed by model)"})
    with pytest.raises(McpToolError, match="not APPROVED"):
        await call_original_tool("submit_nurse_review", {"actor_token": token, "operation": "execute",
                                                         "review_id": rv["review"]["id"]})


async def test_session_token_can_decide_via_mcp(conn, nurse):
    session_token, p = nurse
    token = _dlg(p, {"triage:evaluate", "review:create"})
    ev = await call_original_tool("evaluate_triage_evidence", {"actor_token": token, "encounter_id": "SYN-E-0001",
                                                               "protocol_id": "SYNTHETIC-DEMO-OPD",
                                                               "protocol_version": "0.1.0"})
    rv = await call_original_tool("submit_nurse_review", {"actor_token": token, "operation": "create",
                                                          "encounter_id": "SYN-E-0001",
                                                          "evaluation_id": ev["evaluation_id"],
                                                          "idempotency_key": "y"})
    out = await call_original_tool("submit_nurse_review", {"actor_token": session_token, "operation": "decide",
                                                           "review_id": rv["review"]["id"], "decision": "approve",
                                                           "rationale": "Checked at bedside"})
    assert out["review"]["status"] == "APPROVED"


async def test_invalid_token_and_scope_denied_and_audited(conn, nurse, intake):
    with pytest.raises(McpToolError, match="AUTHENTICATION_FAILED"):
        await call_original_tool("get_patient_context", {"actor_token": "dlg.forged.sig", "patient_id": "SYN-P-0001",
                                                         "encounter_id": "SYN-E-0001"})
    _, clerk = intake
    with pytest.raises(McpToolError, match="PERMISSION_DENIED"):
        await call_original_tool("get_patient_context", {"actor_token": _dlg(clerk, {"context:read"}),
                                                         "patient_id": "SYN-P-0001", "encounter_id": "SYN-E-0001"})
    _, p = nurse
    with pytest.raises(McpToolError, match="PERMISSION_DENIED"):  # token bound to another encounter
        await call_original_tool("get_patient_context", {"actor_token": _dlg(p, {"context:read"}, "SYN-E-0002"),
                                                         "patient_id": "SYN-P-0001", "encounter_id": "SYN-E-0001"})
    outcomes = [r[0] for r in conn.execute("SELECT outcome FROM audit_events WHERE event_type IN "
                                           "('tool_auth_failed','access_denied')")]
    assert outcomes.count("denied") == 3


async def test_ev11_unknown_records_return_errors_not_data(conn, nurse):
    _, p = nurse
    token = _dlg(p, {"context:read"}, "SYN-E-9999")
    with pytest.raises(McpToolError, match="NOT_FOUND"):
        await call_original_tool("get_patient_context", {"actor_token": token, "patient_id": "SYN-P-9999",
                                                         "encounter_id": "SYN-E-9999"})


async def test_ev11_database_failure_reported(conn, nurse, monkeypatch, tmp_path):
    _, p = nurse
    token = _dlg(p, {"context:read"})
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    from hospitalcare.mcp_clients import set_inprocess_server_factory

    set_inprocess_server_factory(lambda: build_server(db_path=blocker / "db.sqlite"))
    try:
        with pytest.raises(McpToolError, match="DATABASE_UNAVAILABLE|unavailable|Error"):
            await call_original_tool("get_patient_context", {"actor_token": token, "patient_id": "SYN-P-0001",
                                                             "encounter_id": "SYN-E-0001"})
    finally:
        set_inprocess_server_factory(None)


async def test_stdio_transport_real_subprocess(conn, nurse, monkeypatch):
    """Spawns `python -m hospitalcare.mcp_server` and calls a tool over real stdio MCP."""
    from hospitalcare import config

    monkeypatch.setenv("HCAI_MCP_TRANSPORT", "stdio")
    config.get_settings.cache_clear()
    _, p = nurse
    out = await call_original_tool("get_patient_context", {"actor_token": _dlg(p, {"context:read"}),
                                                           "patient_id": "SYN-P-0001", "encounter_id": "SYN-E-0001"})
    assert out["context"]["patient"]["id"] == "SYN-P-0001"


async def test_stdio_transport_unavailable_reported(conn, nurse, monkeypatch):
    from hospitalcare import config

    monkeypatch.setenv("HCAI_MCP_TRANSPORT", "stdio")
    config.get_settings.cache_clear()
    monkeypatch.setattr("hospitalcare.mcp_clients.sys.executable", "Z:/definitely/missing/python.exe")
    _, p = nurse
    with pytest.raises(McpToolError, match="unavailable"):
        await call_original_tool("get_patient_context", {"actor_token": _dlg(p, {"context:read"}),
                                                         "patient_id": "SYN-P-0001", "encounter_id": "SYN-E-0001"})


# --- Borrowed filesystem server -----------------------------------------------------------------

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")


@needs_node
@pytest.mark.filesystem_mcp
async def test_filesystem_reads_protocol(env):
    text = await ReadOnlyFilesystemClient().read_text("protocols/SYNTHETIC-DEMO-OPD_v0.1.0.yaml")
    assert "SYNTHETIC DEMONSTRATION PROTOCOL" in text


@needs_node
@pytest.mark.filesystem_mcp
@pytest.mark.parametrize("path", ["../.env", "../../backend/pyproject.toml", "protocols/../../data/x.yaml",
                                  "C:/Windows/win.ini", "/etc/passwd", ".env", "protocols/.hidden.yaml",
                                  "protocols/evil.exe"])
async def test_ev14_client_guard_blocks_paths(env, path):
    with pytest.raises(McpToolError, match="not permitted|escapes"):
        await ReadOnlyFilesystemClient().call("read_text_file", path)


@needs_node
@pytest.mark.filesystem_mcp
@pytest.mark.parametrize("tool", ["write_file", "edit_file", "create_directory", "move_file", "read_media_file"])
async def test_ev14_write_tools_blocked(env, tool):
    with pytest.raises(McpToolError, match="not permitted"):
        await ReadOnlyFilesystemClient().call(tool, "protocols/x.yaml")


@needs_node
@pytest.mark.filesystem_mcp
async def test_ev14_upstream_server_also_blocks_outside_root(env, tmp_path):
    secret = tmp_path / "data" / "secret.yaml"
    secret.parent.mkdir(exist_ok=True)
    secret.write_text("secret: true")
    client = ReadOnlyFilesystemClient()
    with pytest.raises(McpToolError, match="(?i)access denied|outside"):
        await client.call_unchecked("read_text_file", {"path": str(secret)})
    with pytest.raises(McpToolError, match="(?i)access denied|outside"):
        await client.call_unchecked("read_text_file", {"path": str(Path(client.root) / ".." / "data" / "secret.yaml")})


@needs_node
@pytest.mark.filesystem_mcp
async def test_ev14_symlink_escape_blocked(env, tmp_path):
    target = tmp_path / "outside.yaml"
    target.write_text("outside: true")
    link = Path(env["HCAI_REFERENCE_DIR"]) / "protocols" / "link.yaml"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation not permitted on this Windows account")
    with pytest.raises(McpToolError):
        await ReadOnlyFilesystemClient().call("read_text_file", "protocols/link.yaml")
