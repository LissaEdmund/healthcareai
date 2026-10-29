"""Local open-weights model (Ollama) used only for an optional narrative summary (FR-017, D-004).

The model never sees tools, never computes priority, and its output is checked by
`guard_summary` before display. On any failure the caller receives an explicit
status and no fabricated text.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import get_settings

SYSTEM_PROMPT = """You help outpatient triage nurses read SYNTHETIC patient records quickly.
Write a short factual summary (at most 6 sentences) of the FACTS JSON you are given.
Rules you must follow:
- Use only facts present in FACTS. Do not add any number, value, date, test or event that is not in FACTS.
- Do not diagnose. Do not name possible conditions or causes.
- Do not recommend, prescribe or mention medicines or treatments beyond quoting documented ones.
- Do not say or imply that previous treatment failed or that care was wrong.
- Do not judge values: never call anything normal, abnormal, stable, reassuring, concerning, mild or severe.
- Keep the current visit and each previous visit separate; attribute every documented item to its own visit date.
- If something is listed as missing or conflicting, say so plainly.
- Do not state a triage priority; the protocol result is shown separately.
Return plain text only."""

FORBIDDEN_PATTERNS = [
    (re.compile(r"\bdiagnos", re.I), "diagnosis language"),
    (re.compile(r"\b(likely|probably|possibly|suggestive of|consistent with|indicat\w+ (a|an))\b.{0,40}"
                r"\b(infection|disease|malaria|pneumonia|sepsis|syndrome|disorder)", re.I), "diagnostic inference"),
    (re.compile(r"\bprescrib", re.I), "prescribing language"),
    (re.compile(r"\b(should|must|recommend\w*|advise\w*|consider)\b.{0,30}\b(take|give|start|administer|"
                r"medication|medicine|antibiotic|dose)", re.I), "treatment recommendation"),
    (re.compile(r"treatment\s+(has\s+|had\s+)?failed|did\s+not\s+work|was\s+ineffective|failed\s+treatment",
                re.I), "treatment-failure claim"),
    (re.compile(r"\b(DEMO-)?P[1-3]\b|\bpriority\b", re.I), "priority statement"),
    (re.compile(r"\b(stable|unstable|normal|abnormal|unremarkable|reassuring|concerning|worrying|critical|"
                r"serious|mild|severe|within (the )?(normal|expected) (range|limits))\b", re.I), "clinical judgement"),
]
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


class LLMUnavailable(Exception):
    pass


def model_status() -> dict[str, Any]:
    s = get_settings()
    if not s.llm_enabled:
        return {"available": False, "model": s.ollama_model, "detail": "disabled by HCAI_LLM_ENABLED=false"}
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=3)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "model": s.ollama_model,
                "detail": f"Ollama not reachable at {s.ollama_url} ({exc.__class__.__name__}). "
                          "Start it with `ollama serve`."}
    if s.ollama_model not in names and f"{s.ollama_model}:latest" not in names:
        return {"available": False, "model": s.ollama_model,
                "detail": f"model not pulled; run `ollama pull {s.ollama_model}`"}
    return {"available": True, "model": s.ollama_model, "detail": "ok"}


async def generate(prompt: str, *, system: str = SYSTEM_PROMPT) -> str:
    s = get_settings()
    if not s.llm_enabled:
        raise LLMUnavailable("local model disabled (HCAI_LLM_ENABLED=false)")
    body = {"model": s.ollama_model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_predict": 300, "seed": 7}}
    try:
        async with httpx.AsyncClient(timeout=s.ollama_timeout_seconds) as client:
            r = await client.post(f"{s.ollama_url}/api/chat", json=body)
            r.raise_for_status()
            text = r.json()["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise LLMUnavailable(f"local model call failed: {exc.__class__.__name__}: {exc}") from exc
    if not text:
        raise LLMUnavailable("local model returned an empty response")
    return text


def summary_facts(context: dict[str, Any]) -> dict[str, Any]:
    """Reduce patient context to the facts the model may restate."""
    enc = context.get("encounter", {})
    return {
        "current_visit_complaint": enc.get("chief_complaint"),
        "complaint_source": enc.get("complaint_provenance"),
        "current_observations": [
            {"what": o["label"], "value": o["value"], "unit": o["unit"], "verified": o["verification_status"],
             "source": o["provenance"]}
            for o in context.get("current_observations", []) if o["status"] == "active"
        ],
        "current_symptoms": [{"symptom": s["label"], "present": s["present"], "source": s["provenance"]}
                             for s in context.get("current_symptoms", [])],
        "previous_visits": [
            {"visit_date": p["arrived_at"][:10], "complaint_at_that_visit": p["chief_complaint"],
             "documented_at_that_visit": [f"{n['category']}: {n['content']} ({n['source_type']})"
                                          for n in p["notes"]]}
            for p in context.get("previous_encounters", [])
        ],
        "recurring_complaint": (context.get("recurring_complaint") or {}).get("detected"),
        "missing": [m["item"] for m in context.get("missing_information", [])],
        "conflicts": [c["field"] for c in context.get("conflicts", [])],
    }


def guard_summary(text: str, facts: dict[str, Any]) -> list[str]:
    """Return a list of violations; empty means the summary may be shown."""
    violations = [label for pattern, label in FORBIDDEN_PATTERNS if pattern.search(text)]
    fact_text = json.dumps(facts, ensure_ascii=False)
    fact_numbers = {float(n) for n in _NUMBER.findall(fact_text)}
    for n in _NUMBER.findall(text):
        if float(n) not in fact_numbers:
            violations.append(f"unsupported number '{n}'")
    return violations


async def summarize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return {"status", "text", "violations", "model"}; status ∈ GENERATED, GUARD_REJECTED, MODEL_UNAVAILABLE."""
    facts = summary_facts(context)
    model = get_settings().ollama_model
    try:
        text = await generate("FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=1))
    except LLMUnavailable as exc:
        return {"status": "MODEL_UNAVAILABLE", "text": None, "violations": [], "model": model, "error": str(exc)}
    violations = guard_summary(text, facts)
    if violations:
        return {"status": "GUARD_REJECTED", "text": None, "violations": violations, "model": model,
                "error": "AI summary discarded because it contained unsupported content."}
    return {"status": "GENERATED", "text": text, "violations": [], "model": model, "error": None,
            "label": "AI-generated summary of the records above. Verify against the sources."}
