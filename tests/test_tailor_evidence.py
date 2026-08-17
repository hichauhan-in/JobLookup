from __future__ import annotations

from joblookup.config import Settings
from joblookup.tailor.generate import enforce_evidence

CV_TEXT = """
Support Engineer at Contoso. Handled escalations for Windows networking,
wrote PowerShell automation, and ran Azure Log Analytics queries.
"""

PROFILE = {
    "skills": [{"name": "PowerShell"}, {"name": "Azure Log Analytics"}],
    "tools": ["Windows"],
}


def test_claims_the_cv_supports_are_kept():
    content = {"highlighted_skills": ["PowerShell", "Azure Log Analytics"], "upskilling": []}
    kept, moved = enforce_evidence(content, CV_TEXT, PROFILE, Settings())
    assert set(kept["highlighted_skills"]) == {"PowerShell", "Azure Log Analytics"}
    assert moved == []


def test_claims_it_does_not_are_relegated():
    # A prompt asking the model not to invent things is necessary but not
    # sufficient. This is the part that makes it true.
    content = {"highlighted_skills": ["PowerShell", "Kubernetes"], "upskilling": []}
    kept, moved = enforce_evidence(content, CV_TEXT, PROFILE, Settings())
    assert kept["highlighted_skills"] == ["PowerShell"]
    assert moved == ["Kubernetes"]
    assert "Kubernetes" in kept["upskilling"]


def test_partial_matches_do_not_count():
    # "Azure" is in the CV; "Azure Kubernetes Service" is not, and letting a
    # partial match through is how one becomes the other.
    content = {"highlighted_skills": ["Azure Kubernetes Service"], "upskilling": []}
    kept, moved = enforce_evidence(content, CV_TEXT, PROFILE, Settings())
    assert kept["highlighted_skills"] == []
    assert moved == ["Azure Kubernetes Service"]


def test_upskilling_section_can_be_switched_off():
    settings = Settings()
    settings.tailor.include_upskilling_section = False
    content = {"highlighted_skills": ["Kubernetes"], "upskilling": []}
    kept, moved = enforce_evidence(content, CV_TEXT, PROFILE, settings)
    assert kept["upskilling"] == []
    assert moved == ["Kubernetes"]
