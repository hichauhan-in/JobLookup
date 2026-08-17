"""Country packs, the Workday address parser, and the remote filter.

A pack that names a source which no longer exists would render an empty row and
quietly cost the user coverage, so the pack contents are checked against the
live adapter registry rather than trusted.
"""

from __future__ import annotations

import pytest

from joblookup.config import Settings
from joblookup.matching.prefilter import prefilter
from joblookup.sources import regions, registry
from joblookup.sources.ats.boards import parse_workday_url
from joblookup.sources.base import SourceError


class TestRegions:
    def test_india_is_the_default(self):
        assert regions.DEFAULT_REGION == "in"
        assert regions.resolve("").code == "in"
        assert regions.resolve("nonsense").code == "in"

    def test_every_pack_has_a_unique_code(self):
        codes = [region.code for region in regions.all_regions()]
        assert len(codes) == len(set(codes))

    @pytest.mark.parametrize(
        "region", regions.all_regions(), ids=[r.code for r in regions.all_regions()]
    )
    def test_every_pick_is_a_real_source(self, region):
        known = registry.all_adapters()
        for pick in region.picks:
            assert pick.key in known, f"{region.code} recommends '{pick.key}', which does not exist"

    @pytest.mark.parametrize(
        "region", regions.all_regions(), ids=[r.code for r in regions.all_regions()]
    )
    def test_every_pick_says_why(self, region):
        assert region.summary.strip(), f"{region.code} has no summary"
        for pick in region.picks:
            assert pick.why.strip(), f"{region.code}/{pick.key} does not say why it is worth using"

    def test_no_pack_recommends_the_same_source_twice(self):
        for region in regions.all_regions():
            keys = [pick.key for pick in region.picks]
            assert len(keys) == len(set(keys)), f"{region.code} lists a source twice"

    def test_every_pack_turns_something_on_immediately(self):
        # A pack whose every entry needs a key, a company or a login does
        # nothing when applied, which reads as a broken button.
        adapters = registry.all_adapters()
        for region in regions.all_regions():
            instant = [
                pick.key
                for pick in region.picks
                if adapters[pick.key].tier == "a" and not adapters[pick.key].requires_key
            ]
            assert instant, f"{region.code} needs at least one source that works with no setup"

    def test_only_the_remote_pack_filters_by_work_mode(self):
        remote = [region for region in regions.all_regions() if region.remote_only]
        assert [region.code for region in remote] == ["remote"]

    def test_presets_only_set_fields_the_source_has(self):
        adapters = registry.all_adapters()
        for region in regions.all_regions():
            for pick in region.picks:
                if not pick.config:
                    continue
                allowed = {field.key for field in adapters[pick.key].config_fields()}
                unknown = set(pick.config) - allowed
                assert not unknown, f"{region.code}/{pick.key} presets unknown field {unknown}"

    def test_serialises_for_the_browser(self):
        payload = regions.resolve("in").to_dict()
        assert set(payload) == {"code", "name", "summary", "note", "remote_only", "picks"}
        assert all(set(pick) == {"key", "why", "config"} for pick in payload["picks"])


class TestWorkdayAddress:
    @pytest.mark.parametrize(
        "address",
        [
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/",
            "nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA/Role_JR1",
        ],
    )
    def test_accepts_every_shape_a_person_might_paste(self, address):
        assert parse_workday_url(address) == (
            "nvidia.wd5.myworkdayjobs.com",
            "nvidia",
            "NVIDIAExternalCareerSite",
        )

    def test_reads_the_shard_out_of_the_host(self):
        host, tenant, site = parse_workday_url(
            "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site"
        )
        assert (host, tenant, site) == (
            "salesforce.wd12.myworkdayjobs.com",
            "salesforce",
            "External_Career_Site",
        )

    def test_rejects_a_non_workday_address(self):
        with pytest.raises(SourceError, match="myworkdayjobs.com"):
            parse_workday_url("https://boards.greenhouse.io/stripe")

    def test_rejects_a_host_with_no_site_name(self):
        with pytest.raises(SourceError, match="no site name"):
            parse_workday_url("https://nvidia.wd5.myworkdayjobs.com")


class TestRemoteFilter:
    @staticmethod
    def _jobs():
        return [
            {"title": "A", "work_mode": "remote"},
            {"title": "B", "work_mode": "hybrid"},
            {"title": "C", "work_mode": "onsite"},
            {"title": "D", "work_mode": "unknown"},
        ]

    def test_remote_pack_keeps_only_remote(self):
        settings = Settings()
        settings.search.region = "remote"
        kept, dropped = prefilter(self._jobs(), {}, settings)
        assert [job["title"] for job in kept] == ["A"]
        assert dropped["not_remote"] == 3

    def test_a_country_pack_keeps_everything(self):
        settings = Settings()
        settings.search.region = "in"
        kept, dropped = prefilter(self._jobs(), {}, settings)
        assert len(kept) == 4
        assert "not_remote" not in dropped

    def test_remote_only_combines_with_a_country(self):
        # "India, but only remote roles" has to be expressible.
        settings = Settings()
        settings.search.region = "in"
        settings.search.remote_only = True
        kept, dropped = prefilter(self._jobs(), {}, settings)
        assert [job["title"] for job in kept] == ["A"]
        assert dropped["not_remote"] == 3

    def test_the_remote_pack_ignores_the_switch_being_off(self):
        settings = Settings()
        settings.search.region = "remote"
        settings.search.remote_only = False
        kept, _ = prefilter(self._jobs(), {}, settings)
        assert [job["title"] for job in kept] == ["A"]
