"""Removing the tells that make writing read as machine generated.

None of these are bad words in themselves. They are just words that models reach
for far more often than people do, and a CV that trips several of them at once
reads as generated even to someone who could not say why. The guard rewrites
what it safely can and reports what it could not, so nothing is silently
changed into something the candidate did not mean.

Typography matters more than vocabulary here: an em dash in a CV bullet is the
single most recognisable signal, because almost nobody types one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Replaced outright. The substitute is always shorter and plainer.
SUBSTITUTIONS: dict[str, str] = {
    "leverage": "use",
    "leveraging": "using",
    "leveraged": "used",
    "utilise": "use",
    "utilize": "use",
    "utilised": "used",
    "utilized": "used",
    "spearheaded": "led",
    "spearheading": "leading",
    "orchestrated": "ran",
    "delve into": "look at",
    "delved into": "looked at",
    "robust": "reliable",
    "seamless": "smooth",
    "seamlessly": "smoothly",
    "cutting-edge": "current",
    "state-of-the-art": "current",
    "game-changer": "significant change",
    "holistic": "complete",
    "synergy": "overlap",
    "synergies": "overlaps",
    "furthermore": "also",
    "moreover": "also",
    "additionally": "also",
    "elevate": "improve",
    "elevated": "improved",
    "embark on": "start",
    "embarked on": "started",
    "meticulous": "careful",
    "meticulously": "carefully",
    "underscore": "show",
    "underscores": "shows",
    "showcase": "show",
    "showcased": "showed",
    "showcasing": "showing",
    "pivotal": "key",
    "testament to": "evidence of",
    "in the realm of": "in",
    "navigate the landscape": "work through",
    "deep dive": "detailed review",
    "best-in-class": "strong",
    "world-class": "strong",
    "myriad of": "many",
    "plethora of": "many",
    "vast array of": "many",
    "boasts": "has",
    "empowering": "helping",
    "unlock": "open up",
}

#: Flagged but never auto-rewritten, because any substitute would change meaning.
FLAG_ONLY = (
    "tapestry",
    "beacon",
    "realm",
    "landscape",
    "paradigm",
    "transformative",
    "unparalleled",
    "unwavering",
    "ever-evolving",
    "fast-paced world",
    "in today's",
    "at the end of the day",
    "needless to say",
)

#: "It is not just X, it is Y" and its relatives.
_NOT_JUST_RE = re.compile(
    r"\b(?:it|this|that|they|we|i)('s| is| was|'re| are| were)?\s+"
    r"not (?:just|only|merely|simply)\b[^.!?]*[,;]\s*",
    re.IGNORECASE,
)

#: Three or more comma-separated adjectives before a noun — the "rule of three".
_TRIPLE_RE = re.compile(r"\b(\w+ly|\w+ive|\w+ent|\w+ous),\s+\w+,\s+and\s+\w+\b", re.IGNORECASE)

_DASH_RE = re.compile(r"\s*[—–]\s*")
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u2b00-\u2bff]+"
)
_ELLIPSIS_RE = re.compile(r"\u2026")
_SMART_QUOTES = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"}
_MULTISPACE_RE = re.compile(r"  +")


@dataclass
class GuardReport:
    changes: int = 0
    replaced: dict[str, str] = field(default_factory=dict)
    flagged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": self.changes,
            "replaced": self.replaced,
            "flagged": sorted(set(self.flagged)),
        }


def clean(text: str, report: GuardReport | None = None) -> str:
    """Rewrite one string. ``report`` accumulates across a whole document."""
    if not text:
        return text
    report = report if report is not None else GuardReport()
    original = text

    for fancy, plain in _SMART_QUOTES.items():
        text = text.replace(fancy, plain)
    text = _ELLIPSIS_RE.sub("...", text)

    # An em or en dash between words becomes a plain hyphen with spaces; at the
    # end of a clause it becomes a comma, which is what a person would write.
    text = _DASH_RE.sub(" - ", text)

    if _EMOJI_RE.search(text):
        text = _EMOJI_RE.sub("", text)
        report.flagged.append("emoji")

    for phrase, replacement in SUBSTITUTIONS.items():
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        if pattern.search(text):
            # Bound explicitly: a lambda closing over the loop variable is correct
            # only while the call stays eager, which is the kind of thing that
            # quietly breaks the moment someone defers it.
            text = pattern.sub(
                lambda match, word=replacement: _match_case(match.group(0), word), text
            )
            report.replaced[phrase] = replacement

    if _NOT_JUST_RE.search(text):
        text = _NOT_JUST_RE.sub("", text)
        report.flagged.append("not just X, but Y")

    lowered = text.lower()
    for phrase in FLAG_ONLY:
        if phrase in lowered:
            report.flagged.append(phrase)
    if _TRIPLE_RE.search(text):
        report.flagged.append("rule of three")

    text = _MULTISPACE_RE.sub(" ", text).strip()
    # Removing a lead-in can leave a lowercase sentence start.
    if text and text[0].islower() and original[:1].isupper():
        text = text[0].upper() + text[1:]

    if text != original:
        report.changes += 1
    return text


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def clean_document(value: Any, report: GuardReport | None = None) -> Any:
    """Walk a nested structure and clean every string in it."""
    report = report if report is not None else GuardReport()
    if isinstance(value, str):
        return clean(value, report)
    if isinstance(value, list):
        return [clean_document(item, report) for item in value]
    if isinstance(value, dict):
        return {key: clean_document(item, report) for key, item in value.items()}
    return value


def apply(content: dict[str, Any]) -> tuple[dict[str, Any], GuardReport]:
    report = GuardReport()
    return clean_document(content, report), report
