"""Coded vocabularies used for data entry.

The plausibility ranges below are *data-entry validation* limits that reject
typing errors (e.g. a temperature of 370). They are not clinical thresholds and
play no part in triage evaluation.
"""

from __future__ import annotations

OBSERVATION_CODES: dict[str, dict] = {
    "temperature_c": {"label": "Temperature", "unit": "°C", "type": "number", "range": (25.0, 45.0)},
    "heart_rate_bpm": {"label": "Heart rate", "unit": "beats/min", "type": "number", "range": (20, 250)},
    "resp_rate_bpm": {"label": "Respiratory rate", "unit": "breaths/min", "type": "number", "range": (4, 80)},
    "spo2_pct": {"label": "Oxygen saturation", "unit": "%", "type": "number", "range": (50, 100)},
    "systolic_bp_mmhg": {"label": "Systolic BP", "unit": "mmHg", "type": "number", "range": (40, 300)},
    "diastolic_bp_mmhg": {"label": "Diastolic BP", "unit": "mmHg", "type": "number", "range": (20, 200)},
    "pain_score": {"label": "Pain score", "unit": "0-10", "type": "number", "range": (0, 10)},
    "avpu": {"label": "AVPU", "unit": None, "type": "text", "values": ("A", "V", "P", "U")},
    "weight_kg": {"label": "Weight", "unit": "kg", "type": "number", "range": (0.5, 350)},
}

SYMPTOM_CODES: dict[str, str] = {
    "chest_pain": "Chest pain",
    "difficulty_breathing": "Difficulty breathing",
    "fever": "Fever",
    "headache": "Headache",
    "cough": "Cough",
    "abdominal_pain": "Abdominal pain",
    "vomiting": "Vomiting",
    "diarrhoea": "Diarrhoea",
    "convulsion": "Convulsion",
    "bleeding": "Bleeding",
    "dizziness": "Dizziness",
    "rash": "Rash",
}

COMPLAINT_CODES: dict[str, str] = {
    "fever": "Fever",
    "headache": "Headache",
    "cough": "Cough",
    "abdominal_pain": "Abdominal pain",
    "chest_pain": "Chest pain",
    "diarrhoea": "Diarrhoea",
    "back_pain": "Back pain",
    "skin_complaint": "Skin complaint",
    "follow_up": "Follow-up visit",
    "other": "Other",
}

OBSERVATION_SOURCES = ("clinician_measured", "device", "patient_reported", "paper_record_transcribed")
