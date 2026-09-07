"""Reminders, timeline events and prior drafts survive subsequent edits."""

from datetime import datetime, timezone

import pytest

from joblookup import store
from joblookup.services import applications
from tests.test_workbench import seed


def test_status_transitions_are_recorded_and_applied_date_is_stable(database):
    job_id = seed()
    first = store.set_application(job_id, status="applied")
    assert first["applied_at"]
    store.set_application(job_id, status="interviewing")
    last = store.set_application(job_id, status="applied", notes="Sent application")
    assert last["applied_at"] == first["applied_at"]
    assert len(applications.details(job_id)["events"]) == 4


def test_reminders_complete_and_reopen_without_losing_the_due_date(database):
    job_id = seed()
    store.set_application(job_id, status="saved")
    task = applications.add_task(
        job_id, "Follow up with recruiter", datetime.now(timezone.utc), "followup"
    )
    assert applications.agenda()[0]["id"] == task["id"]
    applications.complete_task(task["id"], True)
    assert applications.agenda() == []
    applications.complete_task(task["id"], False)
    assert applications.agenda()[0]["due_at"] == task["due_at"]
    store.delete_application(job_id)
    assert applications.agenda() == []


def test_naive_due_dates_and_untracked_jobs_are_rejected(database):
    job_id = seed()
    with pytest.raises(ValueError, match="Save"):
        applications.add_task(job_id, "Call", datetime.now(timezone.utc), "followup")
    store.set_application(job_id, status="saved")
    with pytest.raises(ValueError, match="timezone"):
        applications.add_task(job_id, "Call", datetime.now(), "followup")


def test_resume_versions_are_immutable_and_flag_new_claims(database):
    job_id = seed()
    with database.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO cv(filename, label, stored_path, raw_text) "
            "VALUES ('resume.txt', 'Base', 'resume.txt', 'Python developer, 3 years.')"
        )
    cv_id = cursor.lastrowid
    store.save_tailored(
        job_id=job_id, cv_id=cv_id, content={}, prep_sheet={}, markdown="Python developer, 3 years."
    )
    first = applications.versions(job_id)[0]["id"]
    store.save_tailored(
        job_id=job_id,
        cv_id=cv_id,
        content={},
        prep_sheet={},
        markdown="Python and Java expert, 10 years.",
    )
    second = applications.versions(job_id)[0]["id"]
    assert applications.get_version(first)["markdown"] == "Python developer, 3 years."
    assert "Java" in applications.get_version(second)["checks"]["new_skill_mentions"]
    assert "10" in applications.get_version(second)["checks"]["new_numeric_claims"]
    store.set_application(job_id, status="applied")
    applications.set_contact(job_id, "Recruiter", "recruiter@example.org", first)
    assert applications.details(job_id)["application"]["submitted_version_id"] == first


def test_existing_drafts_gain_one_history_entry_on_upgrade(database):
    job_id = seed()
    with database.transaction() as conn:
        cv_id = conn.execute(
            "INSERT INTO cv(label, filename, stored_path, raw_text) "
            "VALUES ('Base', 'resume.txt', '', 'Original Python experience')"
        ).lastrowid
        conn.execute(
            "INSERT INTO tailored_cv(job_id, cv_id, markdown) VALUES (?, ?, 'Existing draft')",
            (job_id, cv_id),
        )
    database.apply_schema(database.db_path())
    database.apply_schema(database.db_path())
    versions = applications.versions(job_id)
    assert len(versions) == 1
    assert applications.get_version(versions[0]["id"])["markdown"] == "Existing draft"
