# Third-Party Dependencies and Licences

HospitalCare AI is licensed under Apache-2.0 (see `LICENSE`). All runtime dependencies below use permissive licences compatible with Apache-2.0. Versions are pinned in `backend/uv.lock`, `mcp-filesystem/package-lock.json` and `frontend/package-lock.json`. Licence identifiers were read from installed package metadata on 2026-10-28.

## Direct Python dependencies (backend)

| Package | Version | Licence |
|---|---|---|
| mcp (MCP Python SDK) | 2.3.0 | MIT |
| langgraph | 1.2.18 | MIT |
| langgraph-checkpoint-sqlite | 3.1.2 | MIT |
| fastapi | 0.162.0 | MIT |
| pydantic | 2.14.1 | MIT |
| pydantic-settings | 2.16.2 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| pytest (dev) | 9.2.0 | MIT |
| pytest-asyncio (dev) | 1.4.1 | Apache-2.0 |

Notable transitive dependencies: langchain-core (MIT), langsmith (MIT — tracing force-disabled in `hospitalcare/__init__.py`), starlette (BSD-3-Clause), anyio (MIT), aiosqlite (MIT), cryptography (Apache-2.0 OR BSD-3-Clause), certifi (MPL-2.0, unmodified), orjson (MPL-2.0 AND (Apache-2.0 OR MIT), unmodified), opentelemetry-api (Apache-2.0; API only, no exporter installed), pywin32 (PSF, Windows only). MPL-2.0 components are used unmodified, which is compatible with distribution alongside Apache-2.0 code.

Full list: `uv pip list` in `backend/`.

## Node dependencies

| Package | Version | Licence | Use |
|---|---|---|---|
| @modelcontextprotocol/server-filesystem | 2.0.1 | MIT / Apache-2.0 (upstream repository is transitioning MIT → Apache-2.0) | Borrowed MCP server (read-only, restricted) |
| Frontend packages (react, react-dom, react-router-dom, vite, typescript, @vitejs/plugin-react) | see `frontend/package.json` | MIT / Apache-2.0 (TypeScript) | Web UI |

## Model and runtime (not redistributed)

| Component | Licence | Note |
|---|---|---|
| Ollama 0.40.12 | MIT | Installed separately with winget |
| phi4-mini weights (default) | MIT (Microsoft Phi-4-mini-instruct) | Pulled at setup; not included in the repository |
| qwen2.5:1.5b weights (low-memory fallback) | Apache-2.0 | Optional |
| qwen2.5:3b weights | **Qwen Research License (non-commercial)** — verified with `ollama show qwen2.5:3b --license` | Used during early development only; not recommended for redistribution or commercial use |
