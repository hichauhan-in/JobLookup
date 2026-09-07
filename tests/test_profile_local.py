from joblookup import store
from joblookup.config import Settings
from joblookup.services import profiling


def test_resume_is_usable_without_a_model(database, tmp_path):
    cv_id = store.add_cv(
        label="Resume",
        filename="resume.txt",
        stored_path=tmp_path / "resume.txt",
        mime_type="text/plain",
        raw_text="Example Candidate\n5 years of experience with Python, Azure and Microsoft 365.",
    )
    result = profiling.extract_cv_locally(cv_id, Settings())
    assert result["method"] == "local"
    assert "Python" in [entry["name"] for entry in result["profile"]["skills"]]
    assert result["profile"]["total_years_experience"] == 5
    assert store.get_cv(cv_id)["extract_state"] == "ok"


def test_manual_skills_and_years_survive_profile_rebuild(database):
    settings = Settings()
    profiling.apply_patch(
        settings,
        {
            "skills": [{"name": "Specialist Domain", "core": True}],
            "total_years_experience": 7,
            "target_titles": ["Researcher"],
            "links": ["https://example.org/portfolio"],
        },
    )
    rebuilt = profiling.rebuild(settings)
    assert rebuilt["skills"][0]["name"] == "Specialist Domain"
    assert rebuilt["total_years_experience"] == 7
    assert rebuilt["target_titles"] == ["Researcher"]
    assert rebuilt["links"] == ["https://example.org/portfolio"]


def test_failed_ai_analysis_preserves_local_extraction(database, tmp_path, monkeypatch):
    import pytest

    from joblookup.llm.base import LLMUnavailableError

    cv_id = store.add_cv(
        label="Resume",
        filename="resume.txt",
        stored_path=tmp_path / "resume.txt",
        mime_type="text/plain",
        raw_text="Python and Azure enterprise support.",
    )
    settings = Settings()
    profiling.extract_cv_locally(cv_id, settings)

    def unavailable(*args, **kwargs):
        raise LLMUnavailableError("No provider configured")

    monkeypatch.setattr("joblookup.services.profiling.cv_extract.extract", unavailable)
    with pytest.raises(LLMUnavailableError):
        profiling.extract_cv(cv_id, None, settings)
    assert store.get_cv(cv_id)["extract_state"] == "ok"
    assert store.get_cv(cv_id)["extract_error"] == "No provider configured"
    assert "Python" in [skill["name"] for skill in profiling.rebuild(settings)["skills"]]
