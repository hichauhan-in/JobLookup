"""Every requested query is accounted for without exceeding source budgets."""

from joblookup.models import RawJob
from joblookup.sources.base import FetchContext, SourceError
from joblookup.sources.search_plan import execute_plan


def test_each_role_and_location_is_searched(settings):
    context = FetchContext(settings, queries=["Support", "SRE"], locations=["India", "UK"])
    calls = []

    def fetch(child):
        calls.append((child.queries[0], child.locations[0]))
        return [RawJob(source_key="example", url=f"https://example.org/{len(calls)}")]

    assert len(execute_plan(context, fetch)) == 4
    assert calls == [("Support", "India"), ("Support", "UK"), ("SRE", "India"), ("SRE", "UK")]
    assert all(row["status"] == "complete" for row in context.search_report)


def test_block_keeps_partial_results_and_stops_requests(settings):
    context = FetchContext(settings, queries=["One", "Two", "Three"])

    def fetch(child):
        if child.queries == ["Two"]:
            raise SourceError("Access refused")
        return [RawJob(source_key="example", url="https://example.org/1")]

    assert len(execute_plan(context, fetch)) == 1
    assert [row["status"] for row in context.search_report] == ["complete", "failed", "skipped"]


def test_bounded_queries_report_unsearched_combinations(settings):
    context = FetchContext(settings, queries=[str(index) for index in range(30)])
    execute_plan(context, lambda child: [])
    assert len(context.search_report) == 30
    assert sum(row["status"] == "complete" for row in context.search_report) == 24


def test_repeated_listings_are_deduplicated(settings):
    context = FetchContext(settings, queries=["One", "Two"])
    assert (
        len(
            execute_plan(
                context, lambda child: [RawJob(source_key="example", url="https://example.org/1")]
            )
        )
        == 1
    )


def test_retry_plan_does_not_repeat_completed_queries(settings):
    context = FetchContext(
        settings,
        queries=["One", "Two"],
        config={"_pending_queries": [{"query": "Two", "location": "India"}]},
    )
    execute_plan(context, lambda child: [])
    assert [(row["query"], row["location"]) for row in context.search_report] == [("Two", "India")]


def test_portal_block_preserves_prior_results(settings):
    from joblookup.sources.tier_b.browser import TierBBlocked

    context = FetchContext(settings, queries=["One", "Two", "Three"])

    def fetch(child):
        if child.queries == ["Two"]:
            raise TierBBlocked("Verification wall")
        return [RawJob(source_key="portal", url="https://example.org/1")]

    assert len(execute_plan(context, fetch)) == 1
    assert [row["status"] for row in context.search_report] == ["complete", "failed", "skipped"]


def test_detail_block_stops_later_queries(settings):
    context = FetchContext(settings, queries=["One", "Two"])

    def fetch(child):
        child.stop_reason = "Detail access refused"
        return [RawJob(source_key="portal", url="https://example.org/1")]

    assert len(execute_plan(context, fetch)) == 1
    assert [row["status"] for row in context.search_report] == ["partial", "skipped"]
