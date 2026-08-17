"""Every source has to be able to explain itself.

A source the user cannot work out how to enable is, in practice, a source that
does not exist. These are cheap checks that stop a new adapter shipping without
the setup guidance the Sources screen expects to render.
"""

from __future__ import annotations

import pytest

from joblookup.sources import registry
from joblookup.sources.ats.boards import _BoardAdapter
from joblookup.sources.tier_b.portal import PortalAdapter

ADAPTERS = sorted(registry.all_adapters().values(), key=lambda adapter: adapter.key)
KEYS = [adapter.key for adapter in ADAPTERS]


def test_every_source_is_registered():
    assert len(ADAPTERS) == 30, "expected 8 keyless feeds, 5 keyed, 8 boards and 9 portals"


@pytest.mark.parametrize("adapter", ADAPTERS, ids=KEYS)
class TestSetupGuide:
    def test_has_a_summary(self, adapter):
        guide = adapter.setup_guide()
        assert guide.summary.strip(), f"{adapter.key} has no summary"

    def test_anything_needing_setup_says_how(self, adapter):
        guide = adapter.setup_guide()
        needs_setup = adapter.requires_key or isinstance(adapter, (_BoardAdapter, PortalAdapter))
        if needs_setup:
            assert guide.steps, f"{adapter.key} needs setup but lists no steps"

    def test_serialises_for_the_browser(self, adapter):
        payload = adapter.setup_guide().to_dict()
        assert set(payload) == {"summary", "steps", "links", "examples", "facts", "note"}
        assert all(set(link) == {"label", "url"} for link in payload["links"])
        assert all(set(example) == {"seen", "enter"} for example in payload["examples"])
        assert all(set(fact) == {"label", "value"} for fact in payload["facts"])

    def test_the_dialog_is_never_effectively_empty(self, adapter):
        # A source with no steps, no facts and no examples renders as a title and
        # one line, which reads as a broken help button.
        guide = adapter.setup_guide()
        assert guide.steps or guide.facts or guide.examples, (
            f"{adapter.key} would open an empty help dialog"
        )

    def test_links_are_real_urls(self, adapter):
        for link in adapter.setup_guide().links:
            assert link[1].startswith("https://"), f"{adapter.key} has a non-https link"


@pytest.mark.parametrize(
    "adapter",
    [a for a in ADAPTERS if isinstance(a, _BoardAdapter)],
    ids=[a.key for a in ADAPTERS if isinstance(a, _BoardAdapter)],
)
class TestBoards:
    def test_explains_where_the_company_name_comes_from(self, adapter):
        assert adapter.address_shape, f"{adapter.key} does not say what the address looks like"

    def test_examples_are_a_real_url_and_what_to_type(self, adapter):
        guide = adapter.setup_guide()
        assert len(guide.examples) >= 2, f"{adapter.key} should show at least two examples"
        for seen, enter in guide.examples:
            assert seen.startswith("https://")
            # The value the user types has to actually appear in the address it
            # was taken from, or the example teaches the wrong thing.
            assert enter.lower() in seen.lower()

    def test_the_field_is_named_in_plain_english(self, adapter):
        labels = [field.label for field in adapter.config_fields()]
        # Workday is the one board addressed by URL rather than by short name,
        # and it carries a second field for how many descriptions to fetch.
        assert labels[0] in ("Companies to watch", "Careers page addresses")
        assert "slug" not in " ".join(labels).lower()


@pytest.mark.parametrize(
    "adapter",
    [a for a in ADAPTERS if a.requires_key],
    ids=[a.key for a in ADAPTERS if a.requires_key],
)
def test_keyed_sources_link_to_where_the_key_comes_from(adapter):
    guide = adapter.setup_guide()
    assert guide.links, f"{adapter.key} needs a key but does not link to where to get one"
