from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from joblookup.models import RawJob
from joblookup.sources import normalize as norm


class TestCleanText:
    def test_flattens_html_and_keeps_structure(self):
        html = "<p>First line</p><ul><li>One</li><li>Two</li></ul><script>bad()</script>"
        result = norm.clean_text(html)
        assert "bad()" not in result
        assert "First line" in result
        assert "• One" in result

    def test_unescapes_entities(self):
        assert norm.clean_text("R&amp;D &lt;team&gt;") == "R&D <team>"

    def test_handles_none(self):
        assert norm.clean_text(None) == ""


class TestCompany:
    @pytest.mark.parametrize(
        "left,right",
        [
            ("Acme Corporation Ltd.", "Acme Corporation"),
            ("Acme, Inc.", "Acme"),
            ("ACME GmbH", "acme"),
        ],
    )
    def test_same_employer_normalises_together(self, left, right):
        assert norm.normalize_company(left) == norm.normalize_company(right)

    def test_a_company_actually_called_group_survives(self):
        # Stripping every suffix would leave nothing at all here.
        assert norm.normalize_company("Group") == "group"


class TestTitle:
    def test_strips_hiring_noise(self):
        assert norm.normalize_title("Senior Engineer (m/f/d) - Remote") == "senior engineer"

    def test_expands_abbreviations(self):
        assert norm.normalize_title("Sr. SW Developer") == "senior software developer"


class TestSeniority:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Principal Engineer", "principal"),
            ("Senior Site Reliability Engineer", "senior"),
            ("Graduate Developer", "junior"),
            ("Engineering Manager", "lead"),
            ("Summer Intern", "intern"),
            ("Software Engineer", "mid"),
        ],
    )
    def test_reads_the_title(self, title, expected):
        assert norm.detect_seniority(title) == expected

    def test_falls_back_to_years_in_the_description(self):
        assert norm.detect_seniority("Engineer", "We need 10+ years of experience") == "senior"


class TestWorkMode:
    def test_hybrid_wins_over_remote(self):
        # "Hybrid - 2 days remote" is hybrid, not remote.
        mode = norm.detect_work_mode(title="Engineer", location="Hybrid, London", description="")
        assert mode == "hybrid"

    def test_unknown_when_nothing_says(self):
        assert (
            norm.detect_work_mode(title="Engineer", location="London", description="") == "unknown"
        )


class TestDates:
    def test_iso(self):
        assert norm.parse_date("2026-01-15T10:00:00Z").startswith("2026-01-15")

    def test_epoch_seconds_and_milliseconds(self):
        assert norm.parse_date(1_700_000_000).startswith("2023-11")
        assert norm.parse_date(1_700_000_000_000).startswith("2023-11")

    def test_relative(self):
        parsed = norm.parse_date("3 days ago")
        age = norm.age_days(parsed)
        assert 2.5 < age < 3.5

    def test_rfc_822_from_rss_feeds(self):
        # We Work Remotely sends a numeric offset; other feeds send a zone name.
        assert norm.parse_date("Fri, 14 Aug 2026 10:31:00 +0000") == "2026-08-14T10:31:00+00:00"
        assert norm.parse_date("Fri, 14 Aug 2026 10:31:00 GMT") == "2026-08-14T10:31:00+00:00"

    def test_unparseable_is_none(self):
        # A wrong date is worse than no date: it would hide fresh postings.
        assert norm.parse_date("sometime soon") is None


class TestSalary:
    def test_range_with_symbol(self):
        low, high, currency = norm.parse_salary("Salary: $90,000 - $120,000 per year")
        assert (low, high, currency) == (90000.0, 120000.0, "USD")

    def test_k_notation(self):
        low, high, _ = norm.parse_salary("£60k - £80k")
        assert (low, high) == (60000.0, 80000.0)

    def test_nothing_found(self):
        assert norm.parse_salary("Competitive salary") == (None, None, "")


class TestFingerprint:
    def _job(self, title, company, location):
        return norm.normalize(
            RawJob(
                source_key="t",
                title=title,
                company=company,
                location=location,
                description="x" * 300,
            )
        )

    def test_same_role_on_two_boards_collapses(self):
        left = self._job("Senior Engineer (m/f/d)", "Acme Ltd", "London, UK")
        right = self._job("Sr. Engineer", "Acme", "London, UK")
        assert left.fingerprint == right.fingerprint

    def test_two_cities_stay_separate(self):
        left = self._job("Support Engineer", "Acme", "Dublin, Ireland")
        right = self._job("Support Engineer", "Acme", "Austin, United States")
        assert left.fingerprint != right.fingerprint


def test_normalize_produces_a_usable_record():
    posted = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    job = norm.normalize(
        RawJob(
            source_key="remoteok",
            title="Senior Platform Engineer",
            company="Globex Inc.",
            location="Remote, United States",
            description="<p>Kubernetes and Terraform. " + "x" * 300 + "</p>",
            url="https://example.com/job/1",
            posted_at=posted,
        )
    )
    assert job.company_norm == "globex"
    assert job.seniority == "senior"
    assert job.work_mode == "remote"
    assert "Kubernetes" in job.description
    assert job.searchable().startswith("Senior Platform Engineer")
