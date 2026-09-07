"""Portable restores reject unsafe archives and never include connection secrets."""

import io
import json
import zipfile

import pytest

from joblookup import store
from joblookup.services import applications, backups, workflow
from tests.test_workbench import seed


def test_roundtrip_preserves_data_and_excludes_credentials(database):
    job_id = seed()
    store.save_profile({"target_titles": ["Python Developer"]})
    store.set_application(job_id, status="applied", notes="Follow up")
    workflow.save_track({"name": "Python", "schedule_enabled": True})
    database.set_setting("secret:provider", "private-test-token")
    root = database.db_path().parent
    archive = backups.export_workspace(root)
    preview = backups.preview_workspace(archive)
    assert preview["counts"]["application"] == 1
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        manifest = zipped.read("manifest.json")
    assert b"private-test-token" not in manifest
    store.delete_application(job_id)
    result = backups.restore_workspace(archive, root)
    assert applications.details(job_id)["application"]["notes"] == "Follow up"
    assert workflow.list_tracks()[0]["schedule_enabled"] is False
    assert (root / "backups" / result["safety_backup"]).is_file()
    assert database.get_setting("secret:provider") == "private-test-token"


def test_unsafe_paths_are_rejected_before_any_restore(database):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../outside.txt", "bad")
        archive.writestr("manifest.json", "{}")
    with pytest.raises(ValueError, match="unsafe"):
        backups.preview_workspace(output.getvalue())


def test_unknown_tables_are_rejected(database):
    data = backups.export_workspace(database.db_path().parent)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["tables"]["setting"] = [{"key": "bad", "value": "injected"}]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(ValueError, match="supported"):
        backups.preview_workspace(output.getvalue())


@pytest.mark.parametrize("profile_data", ["[1,2]", "not-json", "null"])
def test_malformed_profile_is_rejected_without_changing_workspace(database, profile_data):
    store.save_profile({"target_titles": ["Python Developer"]})
    original = store.get_profile()
    data = backups.export_workspace(database.db_path().parent)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["tables"]["profile"][0]["data"] = profile_data
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(ValueError, match="profile.data"):
        backups.restore_workspace(output.getvalue(), database.db_path().parent)
    assert store.get_profile() == original


def test_documents_are_restored_inside_the_workspace(database):
    root = database.db_path().parent
    original = root / "resume.txt"
    original.write_text("Python resume", encoding="utf-8")
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO cv(label, filename, stored_path, raw_text) "
            "VALUES ('Base', 'resume.txt', ?, 'Python resume')",
            (str(original),),
        )
    data = backups.export_workspace(root)
    original.unlink()
    backups.restore_workspace(data, root)
    from pathlib import Path

    stored = Path(database.connect().execute("SELECT stored_path FROM cv").fetchone()[0])
    assert stored.is_relative_to(root)
    assert stored.read_text() == "Python resume"
