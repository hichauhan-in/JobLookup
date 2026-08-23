"""Counting what the model costs, and remembering it.

None of the providers JobLookup can talk to reliably report usage: the VS Code
bridge and the Copilot CLI report nothing at all, and only some OpenAI-compatible
endpoints fill in a usage block. So the count here is an estimate, and is
labelled as one everywhere it is shown.

The estimate is deliberately simple. English prose and the JSON this app sends
both land near four characters per token across every tokeniser in common use,
which is close enough to tell a 20,000-token search from a 200,000-token one.
That is the decision this number exists to inform. Anyone wanting exact figures
should read them from their provider's own dashboard, and the UI says so.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

#: Characters per token. Measured against the app's own prompts rather than
#: assumed: JSON payloads sit slightly denser than prose, and this is the middle.
CHARS_PER_TOKEN = 4.0


def estimate(text: str) -> int:
    """Roughly how many tokens a piece of text will become."""
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN))


@dataclass(slots=True)
class Usage:
    """What one purpose cost, summed over however many calls it took."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    #: True when at least one figure came from the provider rather than a guess.
    measured: bool = False

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.measured = self.measured or other.measured

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total,
            "measured": self.measured,
        }


class UsageRecorder:
    """Collects usage across a run, split by what it was spent on.

    Thread-safe because scoring batches and source fetches run in parallel.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_purpose: dict[str, Usage] = {}
        self._models: dict[str, int] = {}

    def record(
        self,
        purpose: str,
        *,
        prompt: str = "",
        reply: str = "",
        model: str = "",
        reported: dict[str, int] | None = None,
    ) -> Usage:
        one = Usage(calls=1)
        if reported and reported.get("input_tokens") is not None:
            one.input_tokens = int(reported.get("input_tokens") or 0)
            one.output_tokens = int(reported.get("output_tokens") or 0)
            one.measured = True
        else:
            one.input_tokens = estimate(prompt)
            one.output_tokens = estimate(reply)

        with self._lock:
            self._by_purpose.setdefault(purpose, Usage()).add(one)
            if model:
                self._models[model] = self._models.get(model, 0) + 1
        return one

    def total(self) -> Usage:
        combined = Usage()
        with self._lock:
            for usage in self._by_purpose.values():
                combined.add(usage)
        return combined

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            purposes = {name: usage.to_dict() for name, usage in self._by_purpose.items()}
            models = dict(self._models)
        combined = self.total().to_dict()
        return {**combined, "by_purpose": purposes, "models": models}


#: The recorder the current run writes to. A module-level handle rather than a
#: parameter threaded through every call site, because scoring, tailoring and CV
#: reading all sit at different depths and none of them should have to care.
_active = threading.local()


def set_recorder(recorder: UsageRecorder | None) -> None:
    _active.recorder = recorder


def recorder() -> UsageRecorder | None:
    return getattr(_active, "recorder", None)


def record(
    purpose: str,
    *,
    prompt: str = "",
    reply: str = "",
    model: str = "",
    reported: dict[str, int] | None = None,
) -> None:
    """Note one model call against the run in progress, if there is one."""
    active = recorder()
    if active is not None:
        active.record(purpose, prompt=prompt, reply=reply, model=model, reported=reported)


@dataclass(slots=True)
class Estimate:
    """What a search is expected to cost before it is run."""

    calls: int
    input_tokens: int
    output_tokens: int
    postings: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total,
            "postings": self.postings,
        }


#: Measured from the app's own scoring prompt. See the audit in the README.
SYSTEM_PROMPT_TOKENS = 480
CANDIDATE_BLOCK_TOKENS = 200
#: Per posting, beyond its description: title, company, location and the like.
POSTING_OVERHEAD_TOKENS = 60


def estimate_search(
    *,
    postings: int,
    batch_size: int,
    description_chars: int,
    rationale_words: int,
) -> Estimate:
    """What scoring this many postings should cost, before running it.

    Used to put a number next to the economy slider, so the trade-off being made
    is visible at the moment it is made rather than after the bill arrives.
    """
    batch_size = max(1, batch_size)
    calls = -(-postings // batch_size)
    per_posting_in = POSTING_OVERHEAD_TOKENS + estimate("x" * description_chars)
    input_tokens = (
        calls * (SYSTEM_PROMPT_TOKENS + CANDIDATE_BLOCK_TOKENS) + postings * per_posting_in
    )
    # A score entry is the numbers, the skill lists and the rationale.
    per_posting_out = 55 + round(rationale_words * 1.4)
    return Estimate(
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=postings * per_posting_out,
        postings=postings,
    )


def humanise(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}k"
    return str(tokens)


@dataclass(slots=True)
class Breakdown:
    """Where the tokens went, for the explanation shown in Settings."""

    label: str
    tokens: int
    share: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tokens": self.tokens,
            "share": round(self.share, 3),
            "note": self.note,
        }


def explain_search(
    estimate_: Estimate, *, batch_size: int, description_chars: int
) -> list[Breakdown]:
    """Split an estimate into the parts a person can actually act on."""
    calls = estimate_.calls
    system = calls * SYSTEM_PROMPT_TOKENS
    candidate = calls * CANDIDATE_BLOCK_TOKENS
    descriptions = estimate_.postings * estimate("x" * description_chars)
    metadata = estimate_.postings * POSTING_OVERHEAD_TOKENS
    output = estimate_.output_tokens
    total = max(1, system + candidate + descriptions + metadata + output)

    parts = [
        Breakdown(
            "Job descriptions",
            descriptions,
            descriptions / total,
            f"{description_chars} characters of each posting. The biggest lever by far.",
        ),
        Breakdown(
            "The model's answers",
            output,
            output / total,
            "Scores, matched skills, gaps and the rationale for each posting.",
        ),
        Breakdown(
            "Scoring instructions",
            system,
            system / total,
            f"Sent once per call, and there are {calls} calls.",
        ),
        Breakdown(
            "Posting details",
            metadata,
            metadata / total,
            "Title, company, location and work mode.",
        ),
        Breakdown(
            "Your profile",
            candidate,
            candidate / total,
            "Your skills and targets, repeated on every call.",
        ),
    ]
    return sorted(parts, key=lambda part: -part.tokens)
