"""One career profile from many CVs.

People keep several versions of their CV — one aimed at support work, one at
engineering, one from three jobs ago. Each is a partial view. Merging them gives
a fuller picture than any single file, and confidence weighting stops a skill
mentioned once in an old draft from carrying the same weight as one that appears
in every version.

The user's own answers always win over anything inferred from a document.
"""

from __future__ import annotations

from typing import Any

from joblookup.config import Settings
from joblookup.models import SENIORITY_LADDER, seniority_rank

LEVEL_RANK = {"unknown": 0, "beginner": 1, "working": 2, "strong": 3, "expert": 4}

#: Keys the user sets directly in the wizard. Never overwritten by extraction.
PREFERENCE_KEYS = (
    "target_titles",
    "locations",
    "work_modes",
    "employment_types",
    "recency_days",
    "work_authorization",
    "exclusions",
    "min_salary",
    "salary_currency",
    "notes",
)


def merge(
    extractions: list[dict[str, Any]],
    preferences: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    documents = [item for item in extractions if isinstance(item, dict) and item]
    total = len(documents) or 1

    profile: dict[str, Any] = {
        "full_name": _first(documents, "full_name"),
        "headline": _first(documents, "headline"),
        "location": _first(documents, "location"),
        "email": _first(documents, "email"),
        "phone": _first(documents, "phone"),
        "links": _union(documents, "links", 10),
        "summary": _longest(documents, "summary"),
        "total_years_experience": max(
            (float(doc.get("total_years_experience") or 0) for doc in documents), default=0.0
        ),
        "seniority": _highest_seniority(documents),
        "roles": _merge_roles(documents),
        "skills": _merge_skills(documents, total, settings),
        "domains": _union(documents, "domains", 20),
        "tools": _union(documents, "tools", 60),
        "education": _merge_education(documents),
        "certifications": _union(documents, "certifications", 30),
        "languages": _union(documents, "languages", 15),
        "source_cv_count": len(documents),
    }

    for key in PREFERENCE_KEYS:
        if key in preferences:
            profile[key] = preferences[key]
    profile.setdefault("target_titles", [])
    profile.setdefault("locations", [])
    profile.setdefault("work_modes", [])
    profile.setdefault("exclusions", [])
    return profile


def _first(documents: list[dict[str, Any]], key: str) -> str:
    for document in documents:
        value = str(document.get(key) or "").strip()
        if value:
            return value
    return ""


def _longest(documents: list[dict[str, Any]], key: str) -> str:
    values = [str(document.get(key) or "").strip() for document in documents]
    return max(values, key=len, default="")


def _union(documents: list[dict[str, Any]], key: str, limit: int) -> list[str]:
    """Preserve first-seen order and case, match case-insensitively."""
    seen: dict[str, str] = {}
    for document in documents:
        for item in document.get(key) or []:
            text = str(item).strip()
            if text and text.lower() not in seen:
                seen[text.lower()] = text
    return list(seen.values())[:limit]


def _highest_seniority(documents: list[dict[str, Any]]) -> str:
    best = -1
    for document in documents:
        best = max(best, seniority_rank(document.get("seniority")))
    return SENIORITY_LADDER[best] if best >= 0 else "mid"


def _merge_skills(
    documents: list[dict[str, Any]], total: int, settings: Settings
) -> list[dict[str, Any]]:
    """A skill in every CV is core. A skill in one old draft is peripheral.

    ``confidence`` is what the matcher uses to decide how much weight a claim
    carries, and it is also what the profile screen shows so the user can see
    why something is ranked where it is.
    """
    merged: dict[str, dict[str, Any]] = {}
    for document in documents:
        for skill in document.get("skills") or []:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            entry = merged.setdefault(
                key,
                {
                    "name": name,
                    "level": "unknown",
                    "years": 0.0,
                    "category": "",
                    "mentions": 0,
                },
            )
            entry["mentions"] += 1
            entry["years"] = max(entry["years"], float(skill.get("years") or 0))
            if LEVEL_RANK.get(str(skill.get("level")), 0) > LEVEL_RANK.get(entry["level"], 0):
                entry["level"] = str(skill.get("level"))
            entry["category"] = entry["category"] or str(skill.get("category") or "")

    threshold = settings.profile.core_skill_threshold
    for entry in merged.values():
        entry["confidence"] = round(entry["mentions"] / total, 3)
        entry["core"] = entry["confidence"] >= threshold

    ordered = sorted(
        merged.values(),
        key=lambda item: (item["confidence"], LEVEL_RANK.get(item["level"], 0), item["years"]),
        reverse=True,
    )
    return ordered[: settings.profile.max_skills]


def _merge_roles(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per job held, with the richest description found for it."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for document in documents:
        for role in document.get("roles") or []:
            if not isinstance(role, dict):
                continue
            title = str(role.get("title") or "").strip()
            company = str(role.get("company") or "").strip()
            if not title:
                continue
            key = (title.lower(), company.lower())
            current = merged.get(key)
            if current is None:
                merged[key] = dict(role)
                continue
            if len(str(role.get("summary") or "")) > len(str(current.get("summary") or "")):
                current["summary"] = role.get("summary")
            existing = {item.lower() for item in current.get("achievements") or []}
            for achievement in role.get("achievements") or []:
                if achievement.lower() not in existing:
                    current.setdefault("achievements", []).append(achievement)
            current["start"] = _earlier(current.get("start"), role.get("start"))
            current["end"] = _later(current.get("end"), role.get("end"))
            current["current"] = bool(current.get("current") or role.get("current"))

    return sorted(
        merged.values(),
        key=lambda role: (bool(role.get("current")), str(role.get("start") or "")),
        reverse=True,
    )


def _earlier(left: Any, right: Any) -> str:
    values = [str(value) for value in (left, right) if str(value or "").strip()]
    return min(values) if values else ""


def _later(left: Any, right: Any) -> str:
    values = [str(value) for value in (left, right) if str(value or "").strip()]
    return max(values) if values else ""


def _merge_education(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for document in documents:
        for entry in document.get("education") or []:
            if not isinstance(entry, dict):
                continue
            degree = str(entry.get("degree") or "").strip()
            if not degree:
                continue
            merged.setdefault(
                degree.lower(),
                {
                    "degree": degree,
                    "institution": str(entry.get("institution") or "").strip(),
                    "year": str(entry.get("year") or "").strip(),
                },
            )
    return list(merged.values())


def profile_text(profile: dict[str, Any]) -> str:
    """The single string that represents the candidate for recall and embedding."""
    parts: list[str] = []
    if profile.get("headline"):
        parts.append(str(profile["headline"]))
    if profile.get("summary"):
        parts.append(str(profile["summary"]))
    titles = profile.get("target_titles") or []
    if titles:
        parts.append("Targeting: " + ", ".join(str(title) for title in titles))
    roles = [
        f"{role.get('title', '')} at {role.get('company', '')}. {role.get('summary', '')}"
        for role in (profile.get("roles") or [])[:8]
    ]
    parts.extend(roles)
    # Core skills are repeated so they weigh more in lexical scoring, which has
    # no other way to know that one term matters more than another.
    core = [skill["name"] for skill in profile.get("skills") or [] if skill.get("core")]
    other = [skill["name"] for skill in profile.get("skills") or [] if not skill.get("core")]
    if core:
        parts.append("Core skills: " + ", ".join(core))
        parts.append(", ".join(core))
    if other:
        parts.append("Other skills: " + ", ".join(other))
    if profile.get("domains"):
        parts.append("Domains: " + ", ".join(str(item) for item in profile["domains"]))
    return "\n".join(part for part in parts if part.strip())
