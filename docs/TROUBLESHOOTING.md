# Troubleshooting

Entries record problems actually encountered during development, with verified fixes.

| Symptom | Root cause | Diagnosis | Verified solution |
|---|---|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | MCP Python SDK 2.x renamed `FastMCP` to `MCPServer` | `uv pip show mcp` shows 2.x | Use `from mcp.server.mcpserver import MCPServer` (already done) |
| MCP tool errors surface as `MCP server unavailable: ExceptionGroup…` | Errors raised inside the client's task group are wrapped in nested `ExceptionGroup`s | Inspect `exc.exceptions` | `_find_tool_error`/`_root_cause` in `mcp_clients.py` unwrap recursively (fixed 2026-10-28) |
| `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` on `/api/reviews/{id}/decision` | FastAPI runs sync dependencies in a threadpool; the async endpoint used the connection on the event-loop thread | Stack trace from `test_ev08_full_flow_over_http` | `check_same_thread=False` for request-scoped connections (each request has its own) |
| Ollama started by the installer stores models on C: | The tray app was launched before `OLLAMA_MODELS` existed in its environment | `ollama` models dir size on F: is 0 | Stop Ollama processes; start `ollama serve` from a shell where `OLLAMA_MODELS=F:\ollama-models` and `OLLAMA_HOST=127.0.0.1:11434` are set (or log out/in after setting the user variable) |
| `ollama app.exe` running but `http://127.0.0.1:11434` refuses connections | The tray app did not spawn the server in this session | `Invoke-RestMethod http://127.0.0.1:11434/api/version` fails | Run `ollama serve` directly |
| Ollama server killed during development | Machine (15 GB RAM) ran low on memory while several processes were running | Background-task notification reported memory pressure | Close other heavy processes; use `qwen2.5:1.5b` (`HCAI_OLLAMA_MODEL`) on low-memory machines; the app degrades to `MODEL_UNAVAILABLE` safely |
| `hcai serve` exits with "Configuration error: HCAI_SECRET_KEY is not set" | `.env` missing or secret left as placeholder | Check `.env` exists at the repo root | Copy `.env.example` → `.env` and set a ≥ 32-character secret |
| Health shows `model.available=false` with "model not pulled" | Configured model not present | `ollama list` | `ollama pull <HCAI_OLLAMA_MODEL>` |
| Filesystem MCP "not installed" | `mcp-filesystem/node_modules` missing | `uv run hcai check` | `npm ci --prefix mcp-filesystem` |
| Symlink-escape test skipped | Windows account lacks symlink privilege | pytest `-rs` output | Enable Developer Mode or run as a user with `SeCreateSymbolicLinkPrivilege` to execute it |
| `Database already seeded` | `hcai seed` run twice | — | `uv run hcai seed --reset` |
