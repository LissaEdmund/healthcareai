# HospitalCare AI

**Agentic outpatient-triage workflow assistant. Prototype. SYNTHETIC DATA ONLY. Not for clinical use.**

HospitalCare AI helps an authorized nurse see a patient's *documented* history, organize current observations with their sources, and compare verified evidence against a configured, versioned triage protocol. The nurse then decides. An approved action, here a clearly labelled **synthetic** queue update, is executed once, verified and written to a tamper-evident audit log.

It does **not** diagnose, prescribe, invent data or thresholds, or change anything without an authenticated human decision. The only protocol shipped is a synthetic placeholder (`SYNTHETIC-DEMO-OPD`), and no real hospital system is connected.

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Docs index: [docs/README.md](docs/README.md) · Safety: [docs/CLINICAL_SAFETY.md](docs/CLINICAL_SAFETY.md) · Demo: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

## Stack

Python 3.12 · FastAPI · LangGraph · MCP Python SDK 2.3 (original server) · `@modelcontextprotocol/server-filesystem` 2.0.1 (borrowed, read-only) · SQLite · Ollama (`phi4-mini`, local) · React + TypeScript + Vite.

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js ≥ 24, [Ollama](https://ollama.com).

```bash
cp .env.example .env              # then set HCAI_SECRET_KEY (≥32 chars) and HCAI_DEMO_PASSWORD
uv sync --directory backend
npm ci --prefix mcp-filesystem
npm ci --prefix frontend
ollama pull phi4-mini             # optional: without it, summaries show MODEL_UNAVAILABLE

cd backend
uv run hcai seed --reset          # create the local DB with synthetic data
uv run hcai check                 # verify config, DB, model, filesystem MCP
uv run hcai serve                 # API → http://127.0.0.1:8000
# second terminal:
cd frontend && npm run dev        # UI  → http://localhost:5173
```

Log in as `nurse.demo`, `nurse2.demo`, `clinician.demo`, `intake.demo`, `auditor.demo` or `admin.demo` with your `HCAI_DEMO_PASSWORD`.

## Tests

```bash
cd backend
uv run pytest                          # full suite (real-model test runs if Ollama is up)
HCAI_SKIP_MODEL_TESTS=1 uv run pytest  # without the model
```

Latest results and the known unresolved failure (EV-16) are in [docs/EVALS.md](docs/EVALS.md).

## Status and limitations

This is a demonstrable prototype, not a production system. Real-world use would require facility authorization, an approved protocol with recorded governance sign-off, privacy and legal review, clinical evaluation, and a security assessment. No regulatory compliance is claimed. See [docs/memory.md](docs/memory.md) for current state and open decisions.

## Licence

Apache-2.0 ([LICENSE](LICENSE)). Third-party licences: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
