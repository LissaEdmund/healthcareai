"""HospitalCare AI — agentic outpatient triage workflow assistant (synthetic-data prototype)."""

import os

# Privacy (NFR-001): langsmith is a transitive dependency of langchain-core/langgraph. Force its
# tracing off so no workflow state can be sent to a hosted service, whatever the shell environment says.
for _var in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[_var] = "false"
os.environ.pop("LANGSMITH_API_KEY", None)
os.environ.pop("LANGCHAIN_API_KEY", None)
