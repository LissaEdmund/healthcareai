"""Local-model summary guard and failure handling (FR-017, EV-12)."""

import os

import pytest

from hospitalcare import config
from hospitalcare.llm import guard_summary, model_status, summarize_context, summary_facts
from hospitalcare.services.context import build_patient_context

FACTS = {"current_observations": [{"what": "Temperature", "value": 37.2}], "previous_visits": [
    {"date": "2026-06-30", "documented": ["documented_treatment: Paracetamol documented as given"]}]}


@pytest.mark.parametrize("text, label", [
    ("The patient likely has malaria given the fever.", "diagnostic inference"),
    ("Findings are diagnostic of migraine.", "diagnosis language"),
    ("The nurse should give paracetamol 500 mg now.", "treatment recommendation"),
    ("Previous treatment failed because the headache came back.", "treatment-failure claim"),
    ("This patient is DEMO-P1.", "priority statement"),
    ("Current vital signs are stable.", "clinical judgement"),
])
def test_guard_rejects_prohibited_content(text, label):
    assert label in guard_summary(text, FACTS)


def test_guard_rejects_unsupported_numbers():
    violations = guard_summary("Temperature 37.2 and oxygen saturation 91%.", FACTS)
    assert violations == ["unsupported number '91'"]


def test_guard_accepts_faithful_summary():
    text = "Temperature recorded as 37.2. On 2026-06-30 paracetamol was documented as given."
    assert guard_summary(text, FACTS) == []


async def test_ev12_model_disabled_reports_unavailable(conn, nurse):
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001")
    out = await summarize_context(ctx)
    assert out["status"] == "MODEL_UNAVAILABLE" and out["text"] is None


async def test_ev12_unreachable_model_reports_unavailable(conn, nurse, monkeypatch):
    monkeypatch.setenv("HCAI_LLM_ENABLED", "true")
    monkeypatch.setenv("HCAI_OLLAMA_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    config.get_settings.cache_clear()
    _, p = nurse
    out = await summarize_context(build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001"))
    assert out["status"] == "MODEL_UNAVAILABLE" and out["text"] is None and "failed" in out["error"]
    assert model_status()["available"] is False


def test_non_loopback_model_url_rejected(monkeypatch):
    monkeypatch.setenv("HCAI_OLLAMA_URL", "https://api.example.com")
    config.get_settings.cache_clear()
    assert any("loopback" in p for p in config.get_settings().validate_for_runtime())


@pytest.mark.model
@pytest.mark.skipif(os.environ.get("HCAI_SKIP_MODEL_TESTS") == "1", reason="model tests disabled")
async def test_real_local_model_summary_is_guarded(conn, nurse, monkeypatch):
    """Runs the configured open-weights model. The summary must either pass the guard or be discarded."""
    monkeypatch.setenv("HCAI_LLM_ENABLED", "true")
    config.get_settings.cache_clear()
    if not model_status()["available"]:
        pytest.skip(f"local model unavailable: {model_status()['detail']}")
    _, p = nurse
    ctx = build_patient_context(conn, p, "SYN-P-0001", "SYN-E-0001")
    out = await summarize_context(ctx)
    print("MODEL OUTPUT STATUS:", out["status"], out.get("violations"), "\n", out.get("text"))
    assert out["status"] in ("GENERATED", "GUARD_REJECTED")
    if out["status"] == "GENERATED":
        assert guard_summary(out["text"], summary_facts(ctx)) == []
    else:
        assert out["text"] is None and out["violations"]


@pytest.mark.xfail(strict=True, reason="EV-16 known limitation: the guard cannot detect facts attributed to the "
                                       "wrong visit (observed with qwen2.5:3b on 2026-10-28)")
def test_ev16_guard_detects_cross_visit_misattribution():
    facts = {"current_visit_complaint": "Headache again since yesterday",
             "previous_visits": [{"visit_date": "2026-09-23",
                                  "complaint_at_that_visit": "Headache recurring, worse in mornings"}]}
    # "worse in the mornings" belongs to the previous visit, not the current complaint.
    assert guard_summary("The current headache is worse in the mornings.", facts) != []
