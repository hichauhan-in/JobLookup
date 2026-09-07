from joblookup.matching.evidence import evaluate_job, role_fit, skill_evidence
from joblookup.sources.normalize import parse_date


def profile():
    return {
        "target_titles": ["Technical Support Engineer"],
        "locations": ["India"],
        "work_modes": ["remote"],
        "seniority": "mid",
        "skills": [{"name": "M365"}, {"name": "SharePoint"}, {"name": "Azure"}],
    }


def posting(**changes):
    result = {
        "id": 1,
        "title": "Technical Support Engineer",
        "company": "Example",
        "location": "Bengaluru, India",
        "country": "India",
        "work_mode": "remote",
        "seniority": "mid",
        "posted_at": parse_date("1 day ago"),
        "description": "Support enterprise customers using Microsoft 365, SharePoint and Azure. "
        "Troubleshoot incidents, document resolutions, and work with the product team.",
    }
    result.update(changes)
    return result


def test_evidence_is_repeatable_and_uses_posting_quotes():
    first = evaluate_job(posting(), profile())
    assert first == evaluate_job(posting(), profile())
    assert first["band"] == "strong"
    assert first["score"] == sum(item["points"] for item in first["criteria"])
    assert {entry["skill"] for entry in first["matched_skills"]} == {"M365", "SharePoint", "Azure"}
    assert "Microsoft 365" in first["matched_skills"][0]["quote"]


def test_shared_technology_does_not_make_an_unrelated_role_relevant():
    result = evaluate_job(posting(title="Financial Controller"), profile())
    assert result["band"] == "excluded"
    assert result["eligible"] is False


def test_country_restrictions_override_a_perfect_skill_match():
    result = evaluate_job(posting(location="Remote, United States", country="US"), profile())
    assert result["band"] == "excluded"
    assert any("outside" in item for item in result["blockers"])


def test_unspecified_remote_location_needs_review():
    result = evaluate_job(posting(location="Remote", country=""), profile())
    assert result["band"] == "review"
    assert result["eligible"] is True
    assert any("confirmation" in item for item in result["warnings"])


def test_missing_date_is_not_presented_as_fresh():
    assert evaluate_job(posting(posted_at=None), profile())["band"] == "review"


def test_old_postings_are_explicitly_excluded():
    result = evaluate_job(posting(posted_at=parse_date("30 days ago")), profile(), recency_days=7)
    assert result["band"] == "excluded"


def test_excess_seniority_is_not_a_strong_match():
    assert evaluate_job(posting(seniority="director"), profile())["band"] == "excluded"


def test_java_is_not_evidenced_by_javascript():
    assert skill_evidence("Build JavaScript applications", "Java") is None


def test_cplusplus_is_not_evidenced_by_csharp():
    assert skill_evidence("Experience in C# and .NET", "C++") is None


def test_role_abbreviations_are_normalized():
    assert role_fit("Senior SRE", ["Site Reliability Engineer"])[0] == 1


def test_no_profile_does_not_produce_recommendations():
    assert evaluate_job(posting(), {})["band"] == "review"


def test_incomplete_descriptions_require_review():
    assert evaluate_job(posting(description="Azure"), profile())["band"] == "review"


def test_title_alone_is_not_a_recommendation_without_skill_evidence():
    result = evaluate_job(
        posting(description="Support customers and solve problems. " * 10), profile()
    )
    assert result["band"] == "review"


def test_a_different_onsite_city_is_not_a_location_match():
    candidate = profile() | {"locations": ["Pune"], "work_modes": ["onsite"]}
    result = evaluate_job(posting(work_mode="onsite", location="Bengaluru, India"), candidate)
    assert result["band"] == "excluded"
    assert any("cities" in reason for reason in result["blockers"])


def test_remote_jobs_can_be_in_another_city_in_the_same_country():
    candidate = profile() | {"locations": ["Pune"]}
    assert evaluate_job(posting(location="Bengaluru, India"), candidate)["band"] == "strong"


def test_explicit_experience_requirements_are_not_ignored():
    candidate = profile() | {"total_years_experience": 3}
    result = evaluate_job(
        posting(description=posting()["description"] + " Minimum 8 years of experience."), candidate
    )
    assert result["band"] == "excluded"


def test_company_age_is_not_an_experience_requirement():
    candidate = profile() | {"total_years_experience": 3}
    result = evaluate_job(
        posting(description=posting()["description"] + " Our company is 30 years old."), candidate
    )
    assert result["band"] == "strong"


def test_work_mode_and_employment_preferences_are_binding():
    candidate = profile() | {"employment_types": ["full-time"]}
    assert evaluate_job(posting(work_mode="onsite"), candidate)["band"] == "excluded"
    assert evaluate_job(posting(employment="contract"), candidate)["band"] == "excluded"


def test_pipeline_does_not_call_a_provider(database):
    from joblookup import store
    from joblookup.config import Settings
    from joblookup.events import NullBus
    from joblookup.matching.pipeline import run_matching
    from joblookup.models import RawJob
    from joblookup.sources.normalize import normalize

    stored = posting()
    store.upsert_job(
        normalize(
            RawJob(
                source_key="remoteok",
                title=stored["title"],
                company=stored["company"],
                location=stored["location"],
                description=stored["description"],
                posted_at=stored["posted_at"],
                work_mode="remote",
                url="https://example.org/job",
            )
        )
    )
    store.save_profile(profile())
    result = run_matching(Settings(), None, NullBus())
    assert result["scored"] == 1
    assert result["model_calls"] == 0
    assert result["mode"] == "local"
