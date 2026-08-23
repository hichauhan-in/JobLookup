"""What we refuse to fetch.

Every source is a third party, and a third party can answer with a redirect.
Following one back into this machine would turn any enabled feed into a way to
read it, so the address is checked at every hop rather than once at the start.
"""

from __future__ import annotations

import pytest

from joblookup.sources.ats.boards import Recruitee, Workday, parse_workday_url
from joblookup.sources.base import SourceError, check_outbound


class TestRefusedAddresses:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8770/api/settings",
            "http://localhost/api/settings",
            "https://[::1]/",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/",
            "http://10.0.0.5/admin",
            "http://172.16.4.4/",
            "http://0.0.0.0/",
        ],
    )
    def test_anything_pointing_inward_is_refused(self, url):
        with pytest.raises(SourceError):
            check_outbound(url)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://example.com/"])
    def test_only_the_web_schemes_are_allowed(self, url):
        with pytest.raises(SourceError, match="Refusing to fetch"):
            check_outbound(url)

    def test_credentials_in_the_host_are_refused(self):
        # The trick that beats a "contains" host check.
        with pytest.raises(SourceError, match="credentials"):
            check_outbound("https://boards.greenhouse.io@127.0.0.1/x")

    @pytest.mark.parametrize(
        "url",
        [
            "https://boards.greenhouse.io/embed/job_board?for=acme",
            "https://api.lever.co/v0/postings/acme",
            "https://8.8.8.8/",
        ],
    )
    def test_a_public_address_is_fine(self, url):
        check_outbound(url)


class TestWorkdayAddresses:
    def test_a_real_address_parses(self):
        host, tenant, site = parse_workday_url(
            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x"
        )
        assert (host, tenant, site) == (
            "nvidia.wd5.myworkdayjobs.com",
            "nvidia",
            "NVIDIAExternalCareerSite",
        )

    @pytest.mark.parametrize(
        "address",
        [
            "https://myworkdayjobs.com@127.0.0.1/Site",
            "https://x.myworkdayjobs.com.attacker.tld/Site",
            "https://myworkdayjobs.com.example.net/Site",
        ],
    )
    def test_a_host_that_merely_contains_the_name_is_refused(self, address):
        with pytest.raises(SourceError):
            parse_workday_url(address)

    def test_an_address_with_no_site_says_so(self):
        with pytest.raises(SourceError, match="no site name"):
            parse_workday_url("https://nvidia.wd5.myworkdayjobs.com")


class TestCompanySlugs:
    def test_workday_is_exempt_because_it_takes_a_url(self):
        assert Workday().slug_is_a_name is False

    def test_every_other_board_expects_a_name(self):
        assert Recruitee().slug_is_a_name is True
