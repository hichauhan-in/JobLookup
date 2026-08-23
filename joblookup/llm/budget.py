"""Automatic model and detail selection, driven by one dial.

The honest position on token cost is that four things decide it, and only one of
them is the model:

1. **How many postings reach the model.** Linear, and it is the Dashboard's
   "how deep to search" dial, because it is a coverage decision only the user
   can make.
2. **How much of each description is sent.** Measured at roughly 90% of the
   input on a real search, which makes it the single biggest lever here.
3. **How much the model writes back.** About a fifth of the total.
4. **Which model answers.** This changes almost nothing about the token count
   and almost everything about what those tokens cost you, because a premium
   model bills at a multiple of a small one.

So this module owns 2, 3 and 4, and deliberately leaves 1 alone. Two dials that
both silently reduce coverage would be impossible to reason about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Size markers beat family names: a "gpt-5-mini" is a small model even though
#: "gpt-5" also appears in the name of large ones, so these are checked first and
#: the most specific marker wins.
#:
#: Matched against the name split into words, never as substrings. "mini" sits
#: inside "gemini", which would otherwise file Gemini Pro as a small model.
_SMALLEST = (("utility", "small"), ("nano",), ("lite",))
_SMALL = frozenset({"mini", "haiku", "flash", "small", "utility", "8b", "7b", "3b"})
_PREMIUM = frozenset({"opus", "pro", "ultra", "thinking", "reasoning", "o1", "o3", "max"})

TIER_LABELS = {
    0: "smallest",
    1: "small and fast",
    2: "balanced",
    3: "most capable",
}

_SPLIT = re.compile(r"[^a-z0-9]+")


def _words(name: str) -> set[str]:
    return {word for word in _SPLIT.split((name or "").lower()) if word}


def model_tier(name: str) -> int:
    """Roughly how expensive a model is to run, from 0 (cheapest) to 3."""
    words = _words(name)
    if any(set(marker) <= words for marker in _SMALLEST):
        return 0
    if words & _SMALL:
        return 1
    if words & _PREMIUM:
        return 3
    # An unrecognised model is assumed mid-range rather than excluded.
    return 2


def rank_models(models: list[str]) -> list[tuple[str, int]]:
    """Available models with their tier, cheapest first."""
    ranked = [(name, model_tier(name)) for name in models if name]
    # A stable secondary sort keeps the choice from flapping between runs.
    ranked.sort(key=lambda entry: (entry[1], entry[0]))
    return ranked


@dataclass(slots=True)
class Budget:
    """Everything the economy dial decides, resolved for one run."""

    economy: int
    model: str
    model_tier: int
    reasoning_effort: str | None
    description_chars: int
    score_batch_size: int
    rationale_words: int
    profile_skills: int
    label: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "economy": self.economy,
            "model": self.model,
            "model_tier": self.model_tier,
            "tier_label": TIER_LABELS.get(self.model_tier, "balanced"),
            "reasoning_effort": self.reasoning_effort,
            "description_chars": self.description_chars,
            "score_batch_size": self.score_batch_size,
            "rationale_words": self.rationale_words,
            "profile_skills": self.profile_skills,
            "label": self.label,
            "note": self.note,
        }


#: The named stops on the dial. Values in between are interpolated, so the slider
#: is continuous but every position has a defensible meaning.
_STOPS: tuple[tuple[int, dict[str, Any]], ...] = (
    (
        0,
        {
            "label": "Bare minimum",
            "tier": 0,
            "description_chars": 600,
            "score_batch_size": 24,
            "rationale_words": 12,
            "profile_skills": 20,
            "reasoning_effort": "none",
            "note": "Titles and the opening lines only. Good for a quick sweep, weaker on "
            "postings that bury the requirements at the bottom.",
        },
    ),
    (
        25,
        {
            "label": "Frugal",
            "tier": 1,
            "description_chars": 1100,
            "score_batch_size": 18,
            "rationale_words": 18,
            "profile_skills": 30,
            "reasoning_effort": "minimal",
            "note": "Enough of each posting to catch the main requirements, on a small fast model.",
        },
    ),
    (
        50,
        {
            "label": "Balanced",
            "tier": 1,
            "description_chars": 1800,
            "score_batch_size": 12,
            "rationale_words": 28,
            "profile_skills": 45,
            "reasoning_effort": "low",
            "note": "The default. Most postings state their requirements well inside this, "
            "and a small model judges them accurately against a fixed profile.",
        },
    ),
    (
        75,
        {
            "label": "Thorough",
            "tier": 2,
            "description_chars": 3200,
            "score_batch_size": 8,
            "rationale_words": 38,
            "profile_skills": 60,
            "reasoning_effort": "medium",
            "note": "Nearly all of a typical posting, judged in smaller batches by a "
            "mid-range model that reads them more carefully.",
        },
    ),
    (
        100,
        {
            "label": "No compromise",
            "tier": 3,
            "description_chars": 6000,
            "score_batch_size": 5,
            "rationale_words": 50,
            "profile_skills": 80,
            "reasoning_effort": "high",
            "note": "Whole postings, small batches, the best model available. Several times "
            "the cost of Balanced for a modest gain in accuracy.",
        },
    ),
)


def _blend(economy: int) -> dict[str, Any]:
    economy = max(0, min(100, int(economy)))
    lower = _STOPS[0]
    upper = _STOPS[-1]
    for index, (position, _) in enumerate(_STOPS):
        if position >= economy:
            upper = _STOPS[index]
            lower = _STOPS[max(0, index - 1)]
            break

    low_at, low = lower
    high_at, high = upper
    if high_at == low_at:
        return dict(low)

    ratio = (economy - low_at) / (high_at - low_at)

    def between(key: str) -> int:
        return round(low[key] + (high[key] - low[key]) * ratio)

    # The nearer named stop supplies the words, so the label always matches
    # something a person can point at.
    nearest = high if ratio >= 0.5 else low
    return {
        "label": nearest["label"],
        "note": nearest["note"],
        "reasoning_effort": nearest["reasoning_effort"],
        "tier": between("tier"),
        "description_chars": between("description_chars"),
        "score_batch_size": max(1, between("score_batch_size")),
        "rationale_words": between("rationale_words"),
        "profile_skills": between("profile_skills"),
    }


def choose_model(models: list[str], wanted_tier: int) -> tuple[str, int]:
    """The cheapest available model at or above the wanted tier.

    Falls back downwards rather than failing: if the seat only offers premium
    models, the economy end of the dial still has to pick something.
    """
    ranked = rank_models(models)
    if not ranked:
        return "", wanted_tier
    for name, tier in ranked:
        if tier >= wanted_tier:
            return name, tier
    return ranked[-1]


def resolve(economy: int, models: list[str]) -> Budget:
    """Turn the dial position into the settings one run should use."""
    blended = _blend(economy)
    model, tier = choose_model(models, blended["tier"])
    return Budget(
        economy=max(0, min(100, int(economy))),
        model=model,
        model_tier=tier,
        reasoning_effort=blended["reasoning_effort"] or None,
        description_chars=blended["description_chars"],
        score_batch_size=blended["score_batch_size"],
        rationale_words=blended["rationale_words"],
        profile_skills=blended["profile_skills"],
        label=blended["label"],
        note=blended["note"],
    )


_WORD = re.compile(r"\S+")


def clamp_words(text: str, limit: int) -> str:
    """Trim a rationale that came back longer than the budget asked for."""
    words = _WORD.findall(text or "")
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(",;:") + "."


def effective(settings: Any, models: list[str]) -> tuple[Any, Budget | None]:
    """Settings as this run should actually use them.

    With auto off, the settings are returned untouched and no budget applies:
    what the user typed is what gets sent. With auto on, the dial overwrites the
    three things that decide cost, and the choice is reported back so the run
    can say what it did.
    """
    if not getattr(settings.llm, "auto", False):
        return settings, None

    resolved = resolve(settings.llm.economy, models)
    tuned = settings.model_copy(deep=True)
    tuned.matching.description_chars = resolved.description_chars
    tuned.matching.score_batch_size = resolved.score_batch_size

    provider = getattr(tuned.llm, tuned.llm.provider, None)
    if provider is not None and resolved.model:
        if hasattr(provider, "model"):
            provider.model = resolved.model
        if hasattr(provider, "reasoning_effort"):
            provider.reasoning_effort = resolved.reasoning_effort
    return tuned, resolved
