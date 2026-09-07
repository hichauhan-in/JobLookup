import pytest

from joblookup.config import Settings
from joblookup.sources import registry
from joblookup.sources.base import FetchContext, SourceError
from joblookup.sources.tier_b.access import public_jobs
from joblookup.sources.tier_b.browser import TierBBlocked

HTML = """<html><head><title>Jobs</title></head><body>
<a href='/login'>Sign in</a>
<div class='base-card'><h3 class='base-search-card__title'>Python Developer</h3>
<h4 class='base-search-card__subtitle'>Example</h4>
<span class='job-search-card__location'>India</span>
<a class='base-card__full-link' href='/jobs/view/12345'>View</a>
<time datetime='2026-09-06'>1 day ago</time></div></body></html>"""


def test_public_linkedin_cards_parse_without_signin():
    adapter = registry.get_adapter("linkedin")
    jobs = public_jobs(adapter.spec, HTML, "https://www.linkedin.com/jobs/search/")
    assert len(jobs) == 1
    assert jobs[0].title == "Python Developer"
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/12345"
    assert jobs[0].posted_at.startswith("2026-09-06")
    assert jobs[0].raw["access"] == "public"


@pytest.mark.parametrize(
    "html,url",
    [
        ("<title>Security check</title>", "https://www.linkedin.com/jobs/search/"),
        (HTML, "https://www.linkedin.com/authwall"),
        ("<form><input type='password'></form>", "https://www.linkedin.com/jobs/"),
        ("<div id='challenge-running'></div>", "https://www.linkedin.com/jobs/"),
    ],
)
def test_login_and_verification_walls_stop_public_access(html, url):
    with pytest.raises(TierBBlocked):
        public_jobs(registry.get_adapter("linkedin").spec, html, url)


def test_unreadable_layout_is_not_reported_as_zero_results():
    with pytest.raises(SourceError, match="No job cards"):
        public_jobs(
            registry.get_adapter("linkedin").spec, "<h1>Jobs</h1>", "https://www.linkedin.com/jobs/"
        )


def test_explicit_empty_results_are_not_an_error():
    assert (
        public_jobs(
            registry.get_adapter("linkedin").spec,
            "<h1>No jobs found</h1>",
            "https://www.linkedin.com/jobs/",
        )
        == []
    )


def test_public_mode_does_not_require_browser_or_session(monkeypatch):
    settings = Settings()
    settings.tier_b.enabled = True
    context = FetchContext(settings=settings, config={"risk_ack": True, "access_mode": "public"})
    monkeypatch.setattr(
        "joblookup.sources.tier_b.browser.availability", lambda: pytest.fail("Browser not needed")
    )
    assert registry.get_adapter("linkedin").is_configured(context) == (True, "")


def test_public_mode_still_requires_optin():
    settings = Settings()
    context = FetchContext(settings=settings, config={"risk_ack": True, "access_mode": "public"})
    assert registry.get_adapter("linkedin").is_configured(context)[0] is False
    settings.tier_b.enabled = True
    context.config["risk_ack"] = False
    assert registry.get_adapter("linkedin").is_configured(context)[0] is False


def test_malicious_card_url_is_not_imported():
    malicious = HTML.replace("/jobs/view/12345", "javascript:alert(1)")
    with pytest.raises(SourceError, match="complete job cards"):
        public_jobs(
            registry.get_adapter("linkedin").spec, malicious, "https://www.linkedin.com/jobs/"
        )


def test_blocked_portal_is_recorded_as_a_failure_not_empty_success(database, monkeypatch):
    from joblookup.events import NullBus
    from joblookup.services.crawl import fetch_one

    settings = Settings()
    settings.tier_b.enabled = True
    adapter = registry.get_adapter("linkedin")
    monkeypatch.setattr(adapter, "is_configured", lambda context: (True, ""))

    def blocked(context):
        raise TierBBlocked("Sign-in wall")

    monkeypatch.setattr(adapter, "fetch", blocked)
    result = fetch_one(adapter, settings, ["Python"], ["India"], NullBus(), lambda: False)
    assert result.status == "failed"
    assert result.error == "Sign-in wall"


def test_public_jobposting_schema_supplies_full_description():
    import json

    from joblookup.sources.tier_b.access import posting_details

    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "description": "Not the job"},
            {
                "@type": "JobPosting",
                "description": "<p>Build Python systems.</p>",
                "datePosted": "2026-09-06",
            },
        ],
    }
    result = posting_details(
        f'<script type="application/ld+json">{json.dumps(payload)}</script>',
        "https://www.linkedin.com/jobs/view/123",
    )
    assert result["description"] == "Build Python systems."
    assert result["posted_at"].startswith("2026-09-06")


def test_public_details_stop_at_login_wall():
    from joblookup.sources.tier_b.access import posting_details

    with pytest.raises(TierBBlocked):
        posting_details("<h1>Login</h1>", "https://www.linkedin.com/authwall")


def test_detail_block_preserves_cards_and_stops_further_requests(monkeypatch):
    import httpx

    adapter = registry.get_adapter("linkedin")
    calls = []

    def response(context, url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return httpx.Response(200, text=HTML, request=httpx.Request("GET", url))
        raise SourceError("Blocked")

    monkeypatch.setattr(adapter, "request", response)
    result = adapter.fetch_public(FetchContext(settings=Settings(), queries=["Python"]))
    assert len(result) == 1
    assert result[0].raw["partial_description"] is True
    assert len(calls) == 2
