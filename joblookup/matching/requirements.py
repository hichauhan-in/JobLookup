"""Classify explicitly stated requirements without inventing missing facts."""

from __future__ import annotations

import re
from functools import lru_cache

IMPORTANCE = {"required": 1.0, "mentioned": 0.65, "optional": 0.2}
_BOUNDARY = re.compile(r"[;\n.!?](?=\s|$)")
_OPTIONAL = re.compile(r"\b(nice[ -]to[ -]have|preferred|desirable|bonus|optional|a plus)\b", re.I)
_REQUIRED = re.compile(r"\b(required|essential|must|mandatory|need|proficient|minimum)\b", re.I)
_NEGATIVE_PREFIX = re.compile(
    r"\b(?:no|without)\s+(?:(?:any|prior|previous|professional)\s+)?$"
    r"|\bno\s+(?:experience|knowledge|background)\s+(?:in|with|of)\s+$"
    r"|\b(?:do not|don't|need not)\s+(?:need|know|have|require)\s+$",
    re.I,
)
_NEGATIVE_SUFFIX = re.compile(
    r"^\s*(?:(?:experience|knowledge|background|skills?|expertise)\s+)?"
    r"(?:(?:is|are)\s+)?(?:not|isn't|aren't)\s+(?:strictly\s+)?"
    r"(?:required|necessary|needed|mandatory)\b",
    re.I,
)


def requirement_context(text: str, start: int, end: int) -> tuple[str, str]:
    left = max(0, start - 150)
    for boundary in _BOUNDARY.finditer(text, left, start):
        left = boundary.end()
    right_match = _BOUNDARY.search(text, end, min(len(text), end + 170))
    right = right_match.start() if right_match else min(len(text), end + 170)
    clause = text[left:right].strip()
    if _NEGATIVE_PREFIX.search(text[left:start]) or _NEGATIVE_SUFFIX.search(text[end:right]):
        return "negated", clause
    markers = []
    for kind, pattern in (("optional", _OPTIONAL), ("required", _REQUIRED)):
        for marker in pattern.finditer(text, left, right):
            distance = max(0, marker.start() - end, start - marker.end())
            between = (
                text[marker.end() : start] if marker.end() <= start else text[end : marker.start()]
            )
            if re.search(r",|\b(?:and|but|while|whereas)\b", between, re.I):
                distance += 100
            markers.append((distance, kind))
    if markers:
        return min(markers)[1], clause
    headings = text[max(0, left - 600) : left].splitlines()
    for heading in reversed(headings):
        cleaned = heading.strip().strip("#*: ").casefold()
        if cleaned in {
            "nice to have",
            "preferred qualifications",
            "preferred skills",
            "bonus",
            "desirable",
        }:
            return "optional", clause
        if cleaned in {
            "requirements",
            "required skills",
            "required qualifications",
            "minimum qualifications",
            "must have",
        }:
            return "required", clause
        if cleaned.startswith(("responsibilities", "benefits", "about us", "what you will do")):
            break
    return "mentioned", clause


@lru_cache(maxsize=4096)
def role_family(title: str) -> str:
    text = title.casefold().replace("-", " ")
    groups = {
        "support": (
            r"\b(?:technical support|cloud support|windows support|support escalation|"
            r"escalation engineer|support engineer)\b"
        ),
        "reliability": r"\b(?:site reliability|sre|devops|platform engineer)\b",
        "frontend": r"\b(?:front end|frontend|ui developer)\b",
        "backend": r"\b(?:back end|backend|server side developer)\b",
        "security": r"\b(?:security|cybersecurity|soc analyst)\b",
        "data": r"\b(?:data analyst|business intelligence|analytics engineer)\b",
        "quality": r"\b(?:quality assurance|qa engineer|test engineer|sdet)\b",
    }
    return next((family for family, pattern in groups.items() if re.search(pattern, text)), "")


@lru_cache(maxsize=4096)
def management_role(title: str) -> bool:
    return bool(re.search(r"\b(manager|director|head of|vice president|vp)\b", title, re.I))
