"""Track schedules survive restarts without replaying earlier days."""

from datetime import datetime

from joblookup.services.scheduled_tracks import due_tracks
from joblookup.services.workflow import save_track


def test_due_track_catches_up_once_per_scheduled_day(database):
    track = save_track({"name": "Daily", "schedule_enabled": True, "schedule_hour": 9})
    assert due_tracks(datetime(2026, 9, 7, 8, 59)) == []
    assert due_tracks(datetime(2026, 9, 7, 14, 0))[0]["id"] == track["id"]
    with database.transaction() as conn:
        conn.execute(
            "UPDATE search_track SET last_slot = '2026-09-07' WHERE id = ?", (track["id"],)
        )
    assert due_tracks(datetime(2026, 9, 7, 15, 0)) == []
    assert due_tracks(datetime(2026, 9, 8, 10, 0))
    assert due_tracks(datetime(2026, 9, 12, 10, 0)) == []
