"""MCP clients used by the agent.

* The original HospitalCare server (stdio subprocess, or in-process for tests).
* The borrowed `@modelcontextprotocol/server-filesystem` server, wrapped by
  `ReadOnlyFilesystemClient`, which permits only read tools and only paths inside
  the configured reference directory (D-008). The upstream server enforces its own
  allowed-directory check as a second layer.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from mcp import Client, StdioServerParameters

from .config import REPO_ROOT, get_settings


class McpToolError(Exception):
    """A tool call returned an error or the server could not be reached."""

    def __init__(self, tool: str, message: str):
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.message = message


def _passthrough_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.startswith("HCAI_")}


def _result_payload(tool: str, result: Any) -> dict[str, Any]:
    if result.is_error:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise McpToolError(tool, text or "tool returned an error")
    if result.structured_content is not None:
        return result.structured_content
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"text": text}


# --- Original server ---------------------------------------------------------------

_inprocess_server_factory = None  # tests may set a factory returning an MCPServer


def set_inprocess_server_factory(factory) -> None:
    global _inprocess_server_factory
    _inprocess_server_factory = factory


@asynccontextmanager
async def original_server() -> AsyncIterator[Client]:
    settings = get_settings()
    if settings.mcp_transport == "inprocess":
        from .mcp_server.server import build_server

        target = (_inprocess_server_factory or build_server)()
    else:
        target = StdioServerParameters(command=sys.executable, args=["-m", "hospitalcare.mcp_server"],
                                       env=_passthrough_env(), cwd=str(REPO_ROOT / "backend"))
    try:
        async with Client(target, read_timeout_seconds=60) as client:
            yield client
    except McpToolError:
        raise
    except Exception as exc:  # spawn/transport failures
        inner = _find_tool_error(exc)
        if inner is not None:
            raise inner from exc
        raise McpToolError("hospitalcare-ai", f"MCP server unavailable: {_root_cause(exc)}") from exc


def _find_tool_error(exc: BaseException) -> McpToolError | None:
    if isinstance(exc, McpToolError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_tool_error(sub)
            if found is not None:
                return found
    return None


def _root_cause(exc: BaseException) -> str:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{exc.__class__.__name__}: {exc}"


async def call_original_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with original_server() as client:
        result = await client.call_tool(tool, arguments)
        return _result_payload(tool, result)


# --- Borrowed filesystem server -----------------------------------------------------------

class ReadOnlyFilesystemClient:
    """Allow-listed, read-only access to the reference directory through the Filesystem MCP server."""

    ALLOWED_TOOLS = frozenset({"read_text_file", "list_directory", "get_file_info", "list_allowed_directories"})
    ALLOWED_SUFFIXES = frozenset({".yaml", ".yml", ".md", ".json", ".txt"})
    DENIED_NAMES = frozenset({".env", ".git", "id_rsa"})

    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().reference_path).resolve()

    def server_parameters(self) -> StdioServerParameters:
        s = get_settings()
        entry = s.filesystem_mcp_entry_path
        if not entry.is_file():
            raise McpToolError("filesystem", f"Filesystem MCP server not installed at {entry} "
                                             "(run: npm install --prefix mcp-filesystem)")
        return StdioServerParameters(command=s.node_executable, args=[str(entry), str(self.root)],
                                     env={}, cwd=str(self.root))

    def check_path(self, relative: str) -> Path:
        """Validate a path relative to the reference root. Raises McpToolError when not permitted."""
        rel = PurePosixPath(relative.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts or (rel.parts and ":" in rel.parts[0]):
            raise McpToolError("filesystem", f"path not permitted: {relative}")
        if any(part in self.DENIED_NAMES or part.startswith(".") for part in rel.parts):
            raise McpToolError("filesystem", f"path not permitted: {relative}")
        target = (self.root / Path(*rel.parts)).resolve() if rel.parts else self.root
        if target != self.root and self.root not in target.parents:
            raise McpToolError("filesystem", f"path escapes the reference directory: {relative}")
        if target.suffix and target.suffix.lower() not in self.ALLOWED_SUFFIXES:
            raise McpToolError("filesystem", f"file type not permitted: {relative}")
        return target

    async def call(self, tool: str, relative_path: str = "") -> dict[str, Any]:
        if tool not in self.ALLOWED_TOOLS:
            raise McpToolError("filesystem", f"tool '{tool}' is not permitted (read-only allow-list)")
        args = {} if tool == "list_allowed_directories" else {"path": str(self.check_path(relative_path))}
        return await self.call_unchecked(tool, args)

    async def call_unchecked(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call the upstream server directly. Used by `call` and by tests of the upstream guard."""
        try:
            async with Client(self.server_parameters(), read_timeout_seconds=30) as client:
                result = await client.call_tool(tool, args)
        except McpToolError:
            raise
        except Exception as exc:
            raise McpToolError("filesystem", f"Filesystem MCP server unavailable: {_root_cause(exc)}") from exc
        return _result_payload(f"filesystem.{tool}", result)

    async def read_text(self, relative_path: str) -> str:
        payload = await self.call("read_text_file", relative_path)
        return payload.get("content") or payload.get("text") or ""
