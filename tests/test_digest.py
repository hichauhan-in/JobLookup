"""Daily briefs contain only unseen eligible postings and due actions."""

from datetime import datetime, timezone

from joblookup import store
from joblookup.services import applications, digest, workflow
from tests.test_workbench import seed


def test_daily_brief_tracks_unseen_postings_and_reminders(database):
    store.save_profile(
        {
            "target_titles": ["Python Developer"],
            "locations": ["India"],
            "skills": [{"name": "Python"}],
        }
    )
    job_id = seed()
    seed("Financial Controller")
    store.set_application(job_id, status="applied")
    applications.add_task(job_id, "Contact recruiter", datetime.now(timezone.utc), "followup")
    brief = digest.daily_brief()
    assert brief["unseen_count"] == 1
    assert brief["recommended_count"] == 1
    assert brief["actions"][0]["title"] == "Contact recruiter"
    assert "Contact recruiter" in digest.markdown_brief(brief)
    workflow.mark_seen([job_id])
    assert digest.daily_brief()["unseen_count"] == 0
