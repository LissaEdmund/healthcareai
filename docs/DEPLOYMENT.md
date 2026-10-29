# Deployment (local prototype)

Verified on Windows 11 Pro (Git Bash / PowerShell), 15 GB RAM, CPU-only inference. Commands are shown for Git Bash; PowerShell equivalents are noted where they differ.

## 1. Prerequisites

| Tool | Version used | Install |
|---|---|---|
| uv | 0.11.11 | https://docs.astral.sh/uv/ |
| Python | 3.12 (managed by uv) | `uv python install 3.12` |
| Node.js | ≥ 24 (26.1.0 used) | https://nodejs.org |
| Ollama | 0.40.12 | `winget install --id Ollama.Ollama -e` |

## 2. Configuration

```bash
cp .env.example .env
# Generate and paste a secret key (≥ 32 chars):
uv run --directory backend python -c "import secrets; print(secrets.token_urlsafe(48))"
# Edit .env: set HCAI_SECRET_KEY and HCAI_DEMO_PASSWORD
```

Environment variables (all prefixed `HCAI_`): see `.env.example` for the full list with comments. Important: `HCAI_OLLAMA_URL` must be a loopback address; `HCAI_DEMO_MODE=true` is required to evaluate the synthetic demo protocol.

## 3. Install dependencies

```bash
uv sync --directory backend                 # Python deps (pinned by uv.lock)
npm ci --prefix mcp-filesystem              # borrowed Filesystem MCP server 2.0.1 (pinned)
npm ci --prefix frontend                    # web UI
```

## 4. Local model

```bash
# Optional: keep model files off the system drive (PowerShell):
#   [Environment]::SetEnvironmentVariable('OLLAMA_MODELS','F:\ollama-models','User')
ollama serve                                # binds 127.0.0.1:11434 by default
ollama pull phi4-mini                       # default (MIT, ~2.5 GB)
# Low-memory alternative: ollama pull qwen2.5:1.5b  and set HCAI_OLLAMA_MODEL=qwen2.5:1.5b
```

The application runs without the model (summaries show `MODEL_UNAVAILABLE`); all deterministic functions keep working.

## 5. Database

```bash
cd backend
uv run hcai init-db        # apply migrations
uv run hcai seed --reset   # (re)create local DB with SYNTHETIC demo data
```

## 6. Start

Two terminals:

```bash
cd backend && uv run hcai serve          # API on http://127.0.0.1:8000  (docs at /docs)
cd frontend && npm run dev               # UI on http://localhost:5173
```

Log in with a demo account (e.g. `nurse.demo`) and the `HCAI_DEMO_PASSWORD` you set.

## 7. Verify

```bash
cd backend
uv run hcai check                                  # config, DB, model, filesystem MCP
curl http://127.0.0.1:8000/api/health              # readiness (no patient data)
uv run pytest                                      # full test suite
HCAI_SKIP_MODEL_TESTS=1 uv run pytest              # without the model
cd ../frontend && npm run typecheck && npm run build
```

## 8. Run the MCP server standalone (optional)

```bash
cd backend && uv run hcai-mcp      # stdio MCP server; tools require a valid actor_token
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
