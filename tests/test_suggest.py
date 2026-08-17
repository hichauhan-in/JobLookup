"""The company catalogue and the suggestions built on it.

The catalogue is data rather than logic, so what matters is that it stays
internally consistent and that the ranking actually differentiates between
people. A suggestion list that is the same for a data engineer and a designer
would be worse than no suggestions at all, so that is asserted directly.
"""

from __future__ import annotations

import pytest

from joblookup.config import Settings
from joblookup.services import suggest
from joblookup.sources import catalogue, registry


def profile(**overrides):
    base = {
        "target_titles": ["Senior Data Engineer"],
        "seniority": "senior",
        "locations": ["Bangalore, India"],
        "skills": [{"name": name} for name in ("Python", "Spark", "Airflow", "SQL")],
        "roles": [{"title": "Data Engineer", "company": "Acme"}],
    }
    base.update(overrides)
    return base


DESIGNER = {
    "target_titles": ["Product Designer"],
    "seniority": "mid",
    "locations": ["London, United Kingdom"],
    "skills": [{"name": name} for name in ("Figma", "UX", "prototyping")],
    "roles": [{"title": "UI Designer", "company": "Acme"}],
}


class TestCatalogue:
    def test_it_is_worth_having(self):
        assert len(catalogue.COMPANIES) >= 150

    def test_every_company_names_a_board_that_exists(self):
        known = set(registry.all_adapters())
        for company in catalogue.COMPANIES:
            assert company.board in known, f"{company.name} names board '{company.board}'"

    def test_no_duplicate_entries(self):
        seen = [(company.board, company.slug) for company in catalogue.COMPANIES]
        assert len(seen) == len(set(seen))

    @pytest.mark.parametrize("company", catalogue.COMPANIES, ids=lambda c: f"{c.board}:{c.slug}")
    def test_each_entry_is_usable(self, company):
        assert company.name.strip()
        assert company.slug.strip()
        assert company.tags, f"{company.name} has no tags, so it can never be matched"
        assert 1 <= company.tier <= 3
        # Workday is addressed by URL; every other board takes a bare name.
        if company.board == "workday":
            assert company.slug.startswith("https://")
            assert "myworkdayjobs.com" in company.slug
        else:
            assert "://" not in company.slug and " " not in company.slug

    def test_workday_addresses_parse(self):
        from joblookup.sources.ats.boards import parse_workday_url

        for company in catalogue.COMPANIES:
            if company.board == "workday":
                host, tenant, site = parse_workday_url(company.slug)
                assert host and tenant and site

    def test_every_tag_is_reachable_from_a_profile(self):
        # A tag no synonym or plain word can match is dead weight in the ranking.
        text = " ".join(
            [tag.replace("-", " ") for tag in catalogue.all_tags()]
            + [word for words in suggest.SYNONYMS.values() for word in words]
        )
        found = suggest.profile_tags({"headline": text})
        missing = set(catalogue.all_tags()) - found
        assert not missing, f"unreachable tags: {sorted(missing)}"


class TestProfileTags:
    def test_it_reads_skills_and_titles(self):
        tags = suggest.profile_tags(profile())
        assert {"data", "backend"} <= tags

    def test_synonyms_count(self):
        tags = suggest.profile_tags({"headline": "I work on machine learning pipelines"})
        assert "ml" in tags

    def test_whole_words_only(self):
        # "user research" must not count as search experience.
        tags = suggest.profile_tags({"headline": "user research and interviews"})
        assert "search" not in tags
        assert "research" in tags

    def test_an_empty_profile_has_no_tags(self):
        assert suggest.profile_tags({}) == set()


class TestRanking:
    def test_different_people_get_different_companies(self):
        settings = Settings()
        engineers = {p.company.name for p in suggest.rank_companies(profile(), settings, limit=15)}
        designers = {p.company.name for p in suggest.rank_companies(DESIGNER, settings, limit=15)}
        assert engineers != designers
        # Some overlap is fine; near-identical lists would mean the ranking is
        # not really reading the profile.
        assert len(engineers & designers) < 10

    def test_a_data_profile_surfaces_data_companies(self):
        picks = suggest.rank_companies(profile(), Settings(), limit=10)
        assert any("data" in pick.company.tags for pick in picks)

    def test_every_pick_explains_itself(self):
        for pick in suggest.rank_companies(profile(), Settings(), limit=20):
            assert pick.reasons, f"{pick.company.name} was suggested with no reason"

    def test_the_limit_is_respected(self):
        assert len(suggest.rank_companies(profile(), Settings(), limit=7)) == 7

    def test_no_board_takes_over_the_shortlist(self):
        picks = suggest.rank_companies(profile(), Settings(), limit=100)
        counts: dict[str, int] = {}
        for pick in picks:
            counts[pick.company.board] = counts.get(pick.company.board, 0) + 1
        assert max(counts.values()) <= int(100 * suggest.BOARD_SHARE) + 1

    def test_it_can_be_limited_to_one_board(self):
        picks = suggest.rank_companies(profile(), Settings(), limit=20, boards=["ashby"])
        assert picks and all(pick.company.board == "ashby" for pick in picks)

    def test_an_empty_profile_still_suggests_something(self):
        picks = suggest.rank_companies({}, Settings(), limit=10)
        assert len(picks) == 10

    def test_grouped_slugs_are_ready_for_the_config_box(self):
        picks = suggest.rank_companies(profile(), Settings(), limit=30)
        grouped = suggest.grouped_slugs(picks)
        assert grouped
        for board, slugs in grouped.items():
            assert len(slugs) == len(set(slugs))
            assert all(isinstance(slug, str) and slug for slug in slugs)
            assert board in registry.all_adapters()


class TestRoleSuggestions:
    def test_nothing_to_work_from_says_so(self):
        result = suggest.suggest_roles({})
        assert result["roles"] == []
        assert "CV" in result["note"]

    def test_rules_reuse_titles_you_have_held(self):
        result = suggest.suggest_roles(profile())
        titles = [role["title"] for role in result["roles"]]
        assert "Data Engineer" in titles
        assert result["source"] == "rules"

    def test_rules_offer_a_step_up(self):
        result = suggest.suggest_roles(profile())
        assert any(role["reach"] == "stretch" for role in result["roles"])

    def test_a_model_answer_is_preferred(self):
        class FakeClient:
            def complete_json(self, system, user):
                return {"roles": [{"title": "Analytics Engineer", "why": "x", "reach": "ready"}]}

        result = suggest.suggest_roles(profile(), FakeClient())
        assert result["source"] == "model"
        assert result["roles"][0]["title"] == "Analytics Engineer"

    def test_a_broken_model_falls_back_rather_than_failing(self):
        class BrokenClient:
            def complete_json(self, system, user):
                raise RuntimeError("no model configured")

        result = suggest.suggest_roles(profile(), BrokenClient())
        assert result["source"] == "rules"
        assert result["roles"]
        assert "no model configured" in result["note"]

    def test_every_suggestion_has_the_shape_the_screen_expects(self):
        for role in suggest.suggest_roles(profile())["roles"]:
            assert set(role) == {"title", "why", "reach"}
            assert role["reach"] in ("ready", "stretch")
