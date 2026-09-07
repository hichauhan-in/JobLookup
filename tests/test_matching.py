from __future__ import annotations

from joblookup.config import Settings
from joblookup.matching.prefilter import prefilter
from joblookup.matching.recall import cosine, query_terms
from joblookup.matching.rerank import assign_band, composite_score
from joblookup.sources.normalize import parse_date


def job(**overrides):
    base = {
        "id": 1,
        "title": "Site Reliability Engineer",
        "company": "Acme",
        "work_mode": "remote",
        "seniority": "senior",
        "posted_at": parse_date("1 day ago"),
        "recall_score": 0.5,
    }
    base.update(overrides)
    return base


class TestQueryTerms:
    def test_drops_stopwords_and_ranks_by_frequency(self):
        terms = query_terms("Kubernetes Kubernetes Terraform the and a role experience")
        assert terms[0] == "kubernetes"
        assert "terraform" in terms
        assert "the" not in terms
        assert "experience" not in terms


class TestCosine:
    def test_identical_vectors(self):
        assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal(self):
        assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_mismatched_lengths_are_zero_not_an_error(self):
        assert cosine([1.0], [1.0, 2.0]) == 0.0


class TestScoring:
    def test_transferable_is_weighted_heavily(self):
        settings = Settings()
        transferable = composite_score(0.2, 0.9, 0.5, settings)
        direct = composite_score(0.9, 0.2, 0.5, settings)
        # An adjacent role should not be far behind an exact match.
        assert transferable > 0.5
        assert abs(direct - transferable) < 0.05

    def test_bands(self):
        settings = Settings()
        assert assign_band(0.8, None, settings) == "strong"
        assert assign_band(0.6, None, settings) == "good"
        assert assign_band(0.4, None, settings) == "stretch"
        assert assign_band(0.1, None, settings) == "rejected"

    def test_a_blocker_overrides_a_high_score(self):
        settings = Settings()
        assert assign_band(0.95, "Requires a security clearance", settings) == "rejected"


class TestPrefilter:
    def test_drops_roles_far_above_the_profile(self):
        settings = Settings()
        profile = {"seniority": "junior"}
        kept, dropped = prefilter([job(seniority="director")], profile, settings)
        assert kept == []
        assert dropped["too_senior"] == 1

    def test_keeps_a_reasonable_stretch(self):
        settings = Settings()
        kept, _ = prefilter([job(seniority="senior")], {"seniority": "mid"}, settings)
        assert len(kept) == 1

    def test_respects_exclusions(self):
        settings = Settings()
        kept, dropped = prefilter(
            [job(title="Sales Engineer")], {"exclusions": ["sales"]}, settings
        )
        assert kept == []
        assert dropped["excluded"] == 1

    def test_unknown_work_mode_is_not_a_mismatch(self):
        # Dropping it would hide every posting from a source that omits the field.
        settings = Settings()
        kept, _ = prefilter([job(work_mode="unknown")], {"work_modes": ["remote"]}, settings)
        assert len(kept) == 1

    def test_wrong_work_mode_is_dropped(self):
        settings = Settings()
        kept, dropped = prefilter([job(work_mode="onsite")], {"work_modes": ["remote"]}, settings)
        assert kept == []
        assert dropped["work_mode"] == 1

    def test_fresher_postings_rank_first(self):
        settings = Settings()
        old = job(id=1, posted_at=parse_date("6 days ago"))
        new = job(id=2, posted_at=parse_date("1 hour ago"))
        kept, _ = prefilter([old, new], {}, settings)
        assert [entry["id"] for entry in kept] == [2, 1]

    def test_remote_does_not_mean_available_in_every_country(self):
        settings = Settings()
        profile = {"locations": ["India"], "work_modes": ["remote"]}
        kept, dropped = prefilter(
            [job(location="Remote, United States only", country="US")], profile, settings
        )
        assert kept == []
        assert dropped["location"] == 1

    def test_worldwide_remote_is_available_in_the_target_country(self):
        settings = Settings()
        kept, _ = prefilter(
            [job(location="Worldwide", country="", work_mode="remote")],
            {"locations": ["India"]},
            settings,
        )
        assert len(kept) == 1

    def test_short_exclusions_do_not_match_inside_other_words(self):
        kept, _ = prefilter([job()], {"exclusions": ["IT"]}, Settings())
        assert len(kept) == 1
