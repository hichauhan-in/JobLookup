"""Guided setup: applying a country pack, and being able to undo it.

The behaviour that matters is that applying a pack leaves nothing half done,
and that undoing it takes back only what it added. A pack that enabled boards
without giving them companies used to read as a button that did nothing, and an
undo that wiped hand-picked companies would be worse than no undo at all.
"""

from __future__ import annotations

from joblookup import store
from joblookup.config import Settings
from joblookup.sources import registry
from joblookup.sources.base import as_list


def profile_with_skills():
    # Sources have to exist before anything can be written against them.
    registry.sync_source_table()
    store.save_profile(
        {
            "headline": "Platform Engineer",
            "seniority": "senior",
            "target_titles": ["Data Engineer"],
            "skills": [{"name": name} for name in ("Python", "AWS", "SQL", "Kubernetes")],
            "roles": [{"title": "Data Engineer", "company": "Acme"}],
        }
    )


def settings_for(code: str) -> Settings:
    values = Settings()
    values.search.region = code
    return values


class TestApplyingAPack:
    def test_it_fills_the_boards_it_switches_on(self, database):
        profile_with_skills()
        report = registry.apply_region("in", settings_for("in"), companies=40)

        assert report["company_count"] > 0
        boards = [
            entry for entry in report["enabled"] if entry["key"] in {"greenhouse", "lever", "ashby"}
        ]
        assert boards, "the pack should have switched on some company boards"
        # The whole point: a board that is on must have something to fetch.
        for entry in boards:
            assert entry["companies"] > 0, f"{entry['name']} was enabled with no companies"

    def test_an_enabled_board_reports_itself_ready(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=40)
        rows = {row["key"]: row for row in registry.list_sources(settings_for("in"))}
        assert rows["greenhouse"]["enabled"] is True
        assert rows["greenhouse"]["ready"] is True

    def test_it_records_which_pack_chose_the_companies(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=40)
        assert registry.source_config("greenhouse")["from_region"] == "in"

    def test_the_companies_suit_the_pack_not_the_saved_region(self, database):
        # Applying the UK pack while the settings still say India must produce
        # UK-appropriate companies, or the button lies about what it did.
        profile_with_skills()
        report = registry.apply_region("gb", settings_for("in"), companies=40)
        assert report["region"] == "gb"
        assert report["company_count"] > 0

    def test_nothing_needing_a_login_is_switched_on(self, database):
        profile_with_skills()
        report = registry.apply_region("in", settings_for("in"), companies=20)
        assert report["needs_login"]
        rows = {row["key"]: row for row in registry.list_sources(settings_for("in"))}
        for key in ("linkedin", "naukri", "instahyre"):
            assert rows[key]["enabled"] is False

    def test_replace_starts_the_list_again(self, database):
        profile_with_skills()
        registry.update_config("greenhouse", {"slugs": ["something-of-mine"]})
        registry.apply_region("in", settings_for("in"), companies=40, replace=True)
        assert "something-of-mine" not in as_list(registry.source_config("greenhouse")["slugs"])

    def test_not_replacing_keeps_what_was_there(self, database):
        profile_with_skills()
        registry.update_config("greenhouse", {"slugs": ["something-of-mine"]})
        registry.apply_region("in", settings_for("in"), companies=40, replace=False)
        assert "something-of-mine" in as_list(registry.source_config("greenhouse")["slugs"])

    def test_the_view_reports_how_many_companies_each_pick_has(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=40)
        view = registry.region_view("in", settings_for("in"))
        greenhouse = next(pick for pick in view["picks"] if pick["key"] == "greenhouse")
        assert greenhouse["company_count"] == len(greenhouse["companies"]) > 0


class TestUndoingAPack:
    def test_it_takes_back_only_what_the_pack_added(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=40)
        # A board the pack never touched, configured by hand.
        registry.update_config("recruitee", {"slugs": ["bunq"]})
        registry.set_enabled("recruitee", True)

        report = registry.clear_region("in")

        assert report["cleared"]
        assert as_list(registry.source_config("greenhouse").get("slugs")) == []
        # Hand-picked companies survive, which is the whole contract.
        assert as_list(registry.source_config("recruitee").get("slugs")) == ["bunq"]

    def test_a_list_you_edited_yourself_is_no_longer_the_packs(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=40)
        # Editing by hand clears the provenance, as the config endpoint does.
        registry.update_config("greenhouse", {"slugs": ["mine"], "from_region": ""})

        registry.clear_region("in")

        assert as_list(registry.source_config("greenhouse").get("slugs")) == ["mine"]

    def test_clearing_twice_is_harmless(self, database):
        profile_with_skills()
        registry.apply_region("in", settings_for("in"), companies=20)
        registry.clear_region("in")
        assert registry.clear_region("in")["cleared"] == []

    def test_clearing_a_pack_that_was_never_applied_does_nothing(self, database):
        registry.sync_source_table()
        assert registry.clear_region("gb")["cleared"] == []
