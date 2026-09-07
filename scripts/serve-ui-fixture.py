"""Isolated, deterministic browser-test data; never opens the real workspace."""

from __future__ import annotations

import os
import tempfile

import uvicorn

from joblookup import store
from joblookup.config import Settings
from joblookup.models import CrawlStats, RawJob
from joblookup.server.app import create_app
from joblookup.sources import registry
from joblookup.sources.normalize import normalize, parse_date


def main() -> None:
    port = int(os.environ.get("JOBLOOKUP_UI_PORT", "8801"))
    with tempfile.TemporaryDirectory(prefix="joblookup-ui-") as directory:
        settings = Settings()
        settings.paths.workspace = directory
        settings.scheduler.enabled = False
        settings.server.port = port
        app = create_app(settings)
        store.save_profile(
            {
                "full_name": "Alex Morgan",
                "headline": "Technical Support Engineer",
                "target_titles": ["Technical Support Engineer", "Customer Success Engineer"],
                "locations": ["India"],
                "work_modes": ["remote", "hybrid"],
                "skills": [
                    {"name": name, "core": True}
                    for name in ("M365", "SharePoint", "Azure", "Python", "Networking")
                ],
                "seniority": "mid",
                "total_years_experience": 5,
                "recency_days": 14,
                "summary": "Technical support engineer with five years "
                "of enterprise cloud experience.",
                "_manual": [
                    "full_name",
                    "headline",
                    "skills",
                    "seniority",
                    "total_years_experience",
                    "summary",
                ],
            }
        )
        postings = [
            (
                "Technical Support Engineer",
                "Northstar",
                "Bengaluru, India",
                "remote",
                "mid",
                "1 day ago",
            ),
            (
                "Senior Technical Support Engineer",
                "Cloudline",
                "Hyderabad, India",
                "hybrid",
                "senior",
                "2 days ago",
            ),
            ("Customer Success Engineer", "Orbit", "India", "remote", "mid", "1 day ago"),
            (
                "Technical Support Engineer",
                "Brightside",
                "Pune, India",
                "remote",
                "mid",
                "3 days ago",
            ),
            ("Technical Support Engineer", "Fieldwork", "Remote", "remote", "mid", "1 day ago"),
            (
                "Technical Support Engineer",
                "Meridian",
                "Remote, United States only",
                "remote",
                "mid",
                "1 day ago",
            ),
            ("Financial Controller", "Ledger", "India", "remote", "mid", "1 day ago"),
        ]
        produced = {}
        for index, (title, company, location, mode, seniority, date) in enumerate(postings):
            raw = RawJob(
                source_key="greenhouse" if index % 2 else "remoteok",
                title=title,
                company=company,
                location=location,
                work_mode=mode,
                description=(
                    f"## About {company}\n\nJoin our support team to help enterprise "
                    "customers build reliable systems.\n\n"
                    "### What you will do\n\n"
                    "- Troubleshoot Microsoft 365 and SharePoint incidents.\n"
                    "- Work with Azure cloud services and Networking.\n"
                    "- Automate repetitive work with Python.\n"
                    "- Collaborate with engineering and document solutions.\n\n"
                    "### Your experience\n\nPractical experience supporting enterprise customers, "
                    "clear written communication, and a thoughtful approach to solving problems."
                ),
                url=f"https://example.org/careers/{index}",
                posted_at=parse_date(date),
                salary_min=1800000 if index == 0 else None,
                salary_max=2600000 if index == 0 else None,
                salary_currency="INR" if index == 0 else "",
            )
            normalized = normalize(raw)
            normalized.seniority = seniority
            normalized.employment = "full-time"
            job_id, _ = store.upsert_job(normalized)
            produced[job_id] = True
        store.set_application(
            list(produced)[0], status="saved", notes="Recruiter follow-up on Friday."
        )
        registry.sync_source_table()
        run_id = store.start_run(["remoteok", "greenhouse"])
        store.link_run_jobs(run_id, produced)
        stats = CrawlStats(fetched=7, kept=7, new=7, by_source={"remoteok": 4, "greenhouse": 3})
        store.finish_run(run_id, status="ok", stats=stats.to_dict())
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
