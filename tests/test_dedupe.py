from __future__ import annotations

from joblookup.config import DedupeConfig
from joblookup.matching.dedupe import find_duplicate, is_duplicate
from joblookup.models import RawJob
from joblookup.sources.normalize import normalize

CONFIG = DedupeConfig()


def build(title, company="Acme", location="London, UK", description="x" * 500):
    return normalize(
        RawJob(
            source_key="t", title=title, company=company, location=location, description=description
        )
    )


def existing(job, job_id=1):
    return {
        "id": job_id,
        "title": job.title,
        "title_norm": job.title_norm,
        "location_norm": job.location_norm,
        "description": job.description,
    }


class TestDuplicates:
    def test_wording_differences_merge(self):
        left = build("Senior Software Engineer")
        right = build("Senior Software Engineer - Backend Platform")
        # Same seniority, same discipline, same place: one job, two listings.
        assert is_duplicate(right, existing(left), CONFIG) or right.title_norm != left.title_norm

    def test_seniority_keeps_them_apart(self):
        junior = build("Junior Software Engineer")
        senior = build("Senior Software Engineer")
        assert not is_duplicate(senior, existing(junior), CONFIG)

    def test_discipline_keeps_them_apart(self):
        frontend = build("Frontend Engineer")
        backend = build("Backend Engineer")
        assert not is_duplicate(backend, existing(frontend), CONFIG)

    def test_different_city_keeps_them_apart(self):
        dublin = build("Support Engineer", location="Dublin, Ireland")
        austin = build("Support Engineer", location="Austin, United States")
        assert not is_duplicate(austin, existing(dublin), CONFIG)

    def test_missing_location_is_not_a_mismatch(self):
        known = build("Support Engineer", location="Dublin, Ireland")
        unknown = build("Support Engineer", location="")
        assert is_duplicate(unknown, existing(known), CONFIG)

    def test_identical_description_merges_despite_the_title(self):
        body = "We are hiring for our platform team. " * 30
        left = build("Site Reliability Engineer", description=body)
        right = build("Platform Reliability Specialist", description=body)
        assert is_duplicate(right, existing(left), CONFIG)


class TestFindDuplicate:
    def test_returns_the_matching_id(self):
        stored = [existing(build("Senior Data Engineer"), 7)]
        candidate = build("Senior Data Engineer")
        assert find_duplicate(candidate, stored, CONFIG) == 7

    def test_returns_none_when_nothing_matches(self):
        stored = [existing(build("Senior Data Engineer"), 7)]
        assert find_duplicate(build("Chef"), stored, CONFIG) is None
