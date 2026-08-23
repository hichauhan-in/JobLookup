"""The economy dial and the token accounting behind it.

The claim this feature makes is that turning the dial down actually sends fewer
tokens, rather than only relabelling things. That is what these assert.
"""

from __future__ import annotations

import pytest

from joblookup import prompts
from joblookup.config import Settings
from joblookup.llm import budget, usage

MODELS = [
    "copilot-utility-small",
    "gpt-4o-mini",
    "claude-haiku-4.5",
    "gemini-3.5-flash",
    "claude-sonnet-5",
    "gpt-5.5",
    "claude-opus-5",
]

PROFILE = {
    "headline": "Support Escalation Engineer",
    "seniority": "mid",
    "target_titles": ["Cloud Support Engineer"],
    "skills": [{"name": f"Skill {n}"} for n in range(90)],
    "roles": [{"title": "Support Engineer", "company": "Acme"}],
}


def jobs(count: int, description_chars: int = 9000):
    return [
        {
            "id": index,
            "title": f"Engineer {index}",
            "company": "Acme",
            "location": "Remote",
            "description": "x" * description_chars,
        }
        for index in range(count)
    ]


class TestModelTiering:
    @pytest.mark.parametrize(
        ("name", "tier"),
        [
            ("copilot-utility-small", 0),
            ("gpt-4o-mini", 1),
            ("gpt-5-mini", 1),
            ("claude-haiku-4.5", 1),
            ("gemini-3.5-flash", 1),
            ("claude-sonnet-5", 2),
            ("gpt-5.5", 2),
            ("grok-4.6", 2),
            ("claude-opus-5", 3),
            ("gemini-3.1-pro-preview", 3),
        ],
    )
    def test_names_land_in_the_right_tier(self, name, tier):
        assert budget.model_tier(name) == tier

    def test_a_size_marker_beats_the_family_name(self):
        # "gpt-5-mini" contains "gpt-5", which also appears in large models.
        assert budget.model_tier("gpt-5-mini") < budget.model_tier("gpt-5.5")

    def test_an_unknown_model_is_treated_as_mid_range(self):
        assert budget.model_tier("something-entirely-new") == 2

    def test_ranking_is_cheapest_first_and_stable(self):
        ranked = budget.rank_models(MODELS)
        assert [tier for _, tier in ranked] == sorted(tier for _, tier in ranked)
        assert budget.rank_models(MODELS) == ranked

    def test_choosing_falls_back_when_nothing_is_cheap_enough(self):
        name, tier = budget.choose_model(["claude-opus-5"], wanted_tier=0)
        assert name == "claude-opus-5" and tier == 3

    def test_choosing_from_nothing_does_not_explode(self):
        assert budget.choose_model([], wanted_tier=2) == ("", 2)


class TestTheDial:
    def test_lower_settings_mean_fewer_tokens_end_to_end(self):
        # The point of the whole feature: this must be a real reduction.
        sizes = []
        for economy in (0, 25, 50, 75, 100):
            resolved = budget.resolve(economy, MODELS)
            prompt = prompts.score_user(
                PROFILE,
                jobs(resolved.score_batch_size),
                resolved.description_chars,
                rationale_words=resolved.rationale_words,
                skill_limit=resolved.profile_skills,
            )
            per_posting = usage.estimate(prompt) / resolved.score_batch_size
            sizes.append(per_posting)
        assert sizes == sorted(sizes), "turning the dial up must send more, not less"
        assert sizes[-1] > sizes[0] * 3, "the range should be worth having"

    def test_every_position_produces_something_usable(self):
        for economy in range(0, 101, 5):
            resolved = budget.resolve(economy, MODELS)
            assert resolved.description_chars > 0
            assert resolved.score_batch_size >= 1
            assert resolved.rationale_words > 0
            assert resolved.profile_skills > 0
            assert resolved.label and resolved.note

    def test_it_is_clamped_rather_than_trusted(self):
        assert budget.resolve(-50, MODELS).economy == 0
        assert budget.resolve(500, MODELS).economy == 100

    def test_cheaper_positions_choose_cheaper_models(self):
        assert budget.resolve(0, MODELS).model_tier <= budget.resolve(50, MODELS).model_tier
        assert budget.resolve(50, MODELS).model_tier <= budget.resolve(100, MODELS).model_tier

    def test_serialises_for_the_browser(self):
        payload = budget.resolve(50, MODELS).to_dict()
        assert {"economy", "model", "tier_label", "description_chars", "label"} <= set(payload)


class TestApplyingToSettings:
    def test_auto_off_changes_nothing(self):
        settings = Settings()
        settings.llm.auto = False
        settings.matching.description_chars = 4321
        tuned, resolved = budget.effective(settings, MODELS)
        assert resolved is None
        assert tuned.matching.description_chars == 4321
        assert tuned is settings

    def test_auto_on_overrides_the_cost_settings(self):
        settings = Settings()
        settings.llm.auto = True
        settings.llm.economy = 0
        settings.matching.description_chars = 4321
        tuned, resolved = budget.effective(settings, MODELS)
        assert resolved is not None
        assert tuned.matching.description_chars == resolved.description_chars < 4321
        assert tuned.matching.score_batch_size == resolved.score_batch_size

    def test_auto_does_not_mutate_what_the_user_saved(self):
        settings = Settings()
        settings.llm.auto = True
        settings.llm.economy = 100
        before = settings.matching.description_chars
        budget.effective(settings, MODELS)
        assert settings.matching.description_chars == before

    def test_auto_sets_the_model_on_the_active_provider(self):
        settings = Settings()
        settings.llm.auto = True
        settings.llm.provider = "vscode"
        settings.llm.economy = 100
        tuned, resolved = budget.effective(settings, MODELS)
        assert tuned.llm.vscode.model == resolved.model
        assert tuned.llm.vscode.reasoning_effort == resolved.reasoning_effort

    def test_auto_leaves_coverage_alone(self):
        # How many postings are scored is the Dashboard's dial, not this one.
        settings = Settings()
        settings.llm.auto = True
        settings.llm.economy = 0
        before = settings.matching.prefilter_keep
        tuned, _ = budget.effective(settings, MODELS)
        assert tuned.matching.prefilter_keep == before


class TestUsageAccounting:
    def test_it_counts_both_directions(self):
        recorder = usage.UsageRecorder()
        recorder.record("scoring", prompt="a" * 400, reply="b" * 80)
        total = recorder.total()
        assert total.calls == 1
        assert total.input_tokens == 100
        assert total.output_tokens == 20
        assert total.total == 120

    def test_provider_figures_win_over_the_estimate(self):
        recorder = usage.UsageRecorder()
        recorder.record(
            "scoring",
            prompt="a" * 4000,
            reply="b" * 4000,
            reported={"input_tokens": 12, "output_tokens": 3},
        )
        total = recorder.total()
        assert (total.input_tokens, total.output_tokens) == (12, 3)
        assert total.measured is True

    def test_it_splits_by_purpose(self):
        recorder = usage.UsageRecorder()
        recorder.record("scoring", prompt="a" * 400)
        recorder.record("tailoring", prompt="a" * 800)
        payload = recorder.to_dict()
        assert set(payload["by_purpose"]) == {"scoring", "tailoring"}
        assert payload["calls"] == 2

    def test_recording_without_a_run_is_harmless(self):
        usage.set_recorder(None)
        usage.record("scoring", prompt="anything")  # must not raise

    def test_the_module_level_recorder_collects(self):
        recorder = usage.UsageRecorder()
        usage.set_recorder(recorder)
        try:
            usage.record("scoring", prompt="a" * 400)
        finally:
            usage.set_recorder(None)
        assert recorder.total().calls == 1


class TestEstimating:
    def test_more_postings_cost_more(self):
        small = usage.estimate_search(
            postings=50, batch_size=12, description_chars=1800, rationale_words=28
        )
        large = usage.estimate_search(
            postings=300, batch_size=12, description_chars=1800, rationale_words=28
        )
        assert large.total > small.total * 5

    def test_description_length_is_the_dominant_lever(self):
        short = usage.estimate_search(
            postings=300, batch_size=12, description_chars=600, rationale_words=28
        )
        long = usage.estimate_search(
            postings=300, batch_size=12, description_chars=6000, rationale_words=28
        )
        assert long.total > short.total * 3

    def test_the_breakdown_accounts_for_everything(self):
        estimate = usage.estimate_search(
            postings=300, batch_size=12, description_chars=1800, rationale_words=28
        )
        parts = usage.explain_search(estimate, batch_size=12, description_chars=1800)
        assert abs(sum(part.share for part in parts) - 1.0) < 0.01
        assert parts[0].label == "Job descriptions"

    def test_humanise_reads_like_a_person_wrote_it(self):
        assert usage.humanise(950) == "950"
        assert usage.humanise(12_400) == "12k"
        assert usage.humanise(2_300_000) == "2.3M"


class TestRationaleTrimming:
    def test_it_leaves_short_text_alone(self):
        assert budget.clamp_words("Three words here", 10) == "Three words here"

    def test_it_trims_an_overlong_answer(self):
        trimmed = budget.clamp_words("one two three four five six", 3)
        assert trimmed == "one two three."

    def test_it_copes_with_nothing(self):
        assert budget.clamp_words("", 5) == ""


class TestStoringWhatItCost:
    @staticmethod
    def _spent(calls=1, tokens=100, purpose="scoring"):
        return {
            "calls": calls,
            "input_tokens": tokens,
            "output_tokens": tokens,
            "total_tokens": tokens * 2,
            "measured": False,
            "by_purpose": {
                purpose: {
                    "calls": calls,
                    "input_tokens": tokens,
                    "output_tokens": tokens,
                    "total_tokens": tokens * 2,
                }
            },
        }

    def test_it_accumulates_rather_than_overwrites(self, database):
        from joblookup import store

        run_id = store.start_run(["remoteok"])
        store.add_run_tokens(run_id, self._spent(calls=2, tokens=100))
        merged = store.add_run_tokens(run_id, self._spent(calls=3, tokens=50))
        # A re-score after a search adds to that search rather than replacing it.
        assert merged["calls"] == 5
        assert merged["total_tokens"] == 300

    def test_it_keeps_purposes_apart(self, database):
        from joblookup import store

        run_id = store.start_run(["remoteok"])
        store.add_run_tokens(run_id, self._spent(purpose="scoring"))
        merged = store.add_run_tokens(run_id, self._spent(purpose="tailoring"))
        assert set(merged["by_purpose"]) == {"scoring", "tailoring"}

    def test_nothing_spent_records_nothing(self, database):
        from joblookup import store

        run_id = store.start_run(["remoteok"])
        assert store.add_run_tokens(run_id, {"calls": 0}) == {}

    def test_a_missing_run_is_not_an_error(self, database):
        from joblookup import store

        assert store.add_run_tokens(9999, self._spent()) == {}

    def test_history_reports_what_a_search_cost(self, database):
        from joblookup import store

        run_id = store.start_run(["remoteok"])
        store.finish_run(run_id, status="ok", stats={"kept": 12})
        store.add_run_tokens(run_id, self._spent(calls=4, tokens=500))
        run = store.search_history()[0]
        assert run["tokens"]["calls"] == 4
        assert run["tokens"]["total_tokens"] == 1000

    def test_the_summary_adds_runs_up(self, database):
        from joblookup import store

        for _ in range(3):
            run_id = store.start_run(["remoteok"])
            store.finish_run(run_id, status="ok", stats={"kept": 10})
            store.add_run_tokens(run_id, self._spent(calls=2, tokens=100))
        summary = store.token_summary()
        assert summary["runs_measured"] == 3
        assert summary["calls"] == 6
        assert summary["total_tokens"] == 600
        assert summary["average_per_run"] == 200

    def test_runs_that_never_called_the_model_are_left_out(self, database):
        from joblookup import store

        quiet = store.start_run(["remoteok"])
        store.finish_run(quiet, status="ok", stats={})
        assert store.token_summary()["runs_measured"] == 0
