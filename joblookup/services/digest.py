"""An on-device brief of unseen opportunities and upcoming next actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from joblookup import store
from joblookup.matching.evidence import evaluate_job
from joblookup.services import applications, workflow


def daily_brief(track_id: int = 0) -> dict[str, Any]:
    profile = workflow.effective_profile(track_id)
    track = workflow.get_track(track_id) if track_id else None
    seen = workflow.seen_hashes(track_id)
    items = []
    for job in store.match_candidates():
        if job["hidden"] or seen.get(job["id"]) == workflow.posting_hash(job):
            continue
        if (
            track
            and track["sources"]
            and not set(track["sources"]).intersection(job["source_keys"])
        ):
            continue
        fit = evaluate_job(job, profile, recency_days=int(profile.get("recency_days") or 14))
        if fit["eligible"]:
            items.append(
                {
                    "id": job["id"],
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "score": fit["score"],
                    "band": fit["band"],
                    "state": "changed" if job["id"] in seen else "new",
                }
            )
    items.sort(key=lambda job: job["score"], reverse=True)
    now = datetime.now(timezone.utc)
    due = []
    for task in applications.agenda():
        moment = datetime.fromisoformat(task["due_at"].replace("Z", "+00:00"))
        if moment <= now + timedelta(days=7):
            due.append(task | {"overdue": moment < now})
    return {
        "generated_at": now.isoformat(),
        "track_id": track_id,
        "track_name": track["name"] if track else "Main profile",
        "unseen_count": len(items),
        "recommended_count": sum(item["band"] in {"strong", "good"} for item in items),
        "review_count": sum(item["band"] == "review" for item in items),
        "items": items[:20],
        "actions": due,
        "runs": store.search_history(limit=3),
    }


def markdown_brief(brief: dict[str, Any]) -> str:
    def line(value: Any) -> str:
        return " ".join(str(value).split())

    lines = [
        "# JobLookup daily brief",
        "",
        f"Generated: {brief['generated_at']}",
        f"Track: {line(brief['track_name'])}",
        "",
        f"{brief['recommended_count']} new or changed recommendations; "
        f"{brief['review_count']} need review.",
        "",
        "## Opportunities",
        "",
    ]
    lines.extend(
        f"- {line(item['title'])} at {line(item['company'])} ({line(item['location'])}): "
        f"{item['score']}/100, {item['band']}."
        for item in brief["items"]
    )
    lines.extend(["", "## Next actions", ""])
    lines.extend(
        f"- {'OVERDUE: ' if item['overdue'] else ''}{line(item['title'])} / "
        f"{line(item['company'])}: {item['due_at']}"
        for item in brief["actions"]
    )
    lines.extend(
        [
            "",
            "Scores are local evidence, not hiring probabilities. "
            "Availability and eligibility may need confirmation.",
            "",
        ]
    )
    return "\n".join(lines)
